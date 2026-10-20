"""Pure transaction enrichment: tx_type classification, internal-transfer pairing, credit-limit resolution."""

from __future__ import annotations

import pandas as pd

_PAYMENT_KEYWORDS = r"payment|paiement|prélèvement|prelevement|transfer|xfer"
_REFUND_KEYWORDS = r"cashback|cash.?back|remise|refund|rebate|return"
_TRANSFER_MATCH_DAYS = 5


def detect_internal_transfers(df: pd.DataFrame) -> pd.Series:
    """Flag both legs of a transfer between two of the user's own accounts.

    A pair is an outflow (amount > 0) and an inflow (amount < 0) of the same
    magnitude, on two *different* accounts, within _TRANSFER_MATCH_DAYS days.
    Matching is greedy and one-to-one: each row can be consumed by one pair only,
    so three $500 outflows never mark the same $500 inflow three times.

    Money arriving with no matching outgoing leg in the data is left unflagged —
    an inbound e-transfer from another person is income, not a transfer.
    """
    is_paired = pd.Series(False, index=df.index)
    if df.empty:
        return is_paired

    abs_amount = df["amount"].abs().round(2)
    for _, bucket in df.groupby(abs_amount).groups.items():
        bucket_idx = list(bucket)
        if len(bucket_idx) < 2:
            continue
        outflows = [i for i in bucket_idx if df.loc[i, "amount"] > 0]
        inflows = [i for i in bucket_idx if df.loc[i, "amount"] < 0]
        if not outflows or not inflows:
            continue
        unmatched_inflows = set(inflows)
        outflows_sorted = sorted(outflows, key=lambda i: df.loc[i, "date"])
        for out_idx in outflows_sorted:
            out_date = df.loc[out_idx, "date"]
            out_account = df.loc[out_idx, "account_name"]
            candidates = [
                in_idx
                for in_idx in unmatched_inflows
                if df.loc[in_idx, "account_name"] != out_account
                and abs((df.loc[in_idx, "date"] - out_date).days) <= _TRANSFER_MATCH_DAYS
            ]
            if not candidates:
                continue
            best = min(candidates, key=lambda i: abs((df.loc[i, "date"] - out_date).days))
            unmatched_inflows.discard(best)
            is_paired.loc[out_idx] = True
            is_paired.loc[best] = True

    return is_paired


def classify_tx_type(df: pd.DataFrame) -> pd.Series:
    """Classify each row as 'income', 'expense', or 'transfer'.

    Sign convention (Plaid): positive amount = outflow; negative = inflow.
    adjusted_amount = -amount, so positive adjusted_amount = income/gain.

    Invariant: no row on a credit account is ever classified 'income' — a
    credit-account inflow is either a refund (netted against expense) or a
    card payment (transfer), never new money. Internal transfers between the
    user's own accounts (matched pairs via detect_internal_transfers) are
    excluded from both income and expense on both legs; unpaired inflows on
    depository/investment accounts stay 'income' since they may be money from
    someone else (e.g. an incoming e-transfer), which keyword matching alone
    cannot distinguish from an internal transfer.
    """
    types = pd.Series("expense", index=df.index)

    is_depository_or_investment = df["account_type"].isin(["depository", "investment"])
    is_credit = df["account_type"] == "credit"
    is_unknown = ~is_depository_or_investment & ~is_credit  # NULL or unrecognized

    # Depository / investment: negative amount = money arriving = income
    types[is_depository_or_investment & (df["amount"] < 0)] = "income"
    # Depository / investment: positive amount with payment keyword = transfer
    types[
        is_depository_or_investment
        & (df["amount"] > 0)
        & df["description"].str.contains(_PAYMENT_KEYWORDS, case=False, na=False)
    ] = "transfer"

    # Credit card: positive = purchase = expense (default already set)
    # Credit card: negative + refund keyword = reversal of a purchase = expense (nets against spend)
    types[
        is_credit
        & (df["amount"] < 0)
        & df["description"].str.contains(_REFUND_KEYWORDS, case=False, na=False)
    ] = "expense"
    # Credit card: negative without refund keyword = payment received = transfer
    types[
        is_credit
        & (df["amount"] < 0)
        & ~df["description"].str.contains(_REFUND_KEYWORDS, case=False, na=False)
    ] = "transfer"

    # Unknown account_type: treat negative amounts as income (conservative fallback)
    types[is_unknown & (df["amount"] < 0)] = "income"

    # Internal transfers (matched pairs across the user's own accounts) override
    # everything above — applied last so a paired inflow flips from income/expense
    # to transfer on both legs.
    types[detect_internal_transfers(df)] = "transfer"

    return types


def enrich_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """Add adjusted_amount, month, week, and tx_type columns. Call once before tabs."""
    df = df.copy()
    df["adjusted_amount"] = -df["amount"]
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["week"] = df["date"].dt.to_period("W-SUN").astype(str)
    df["tx_type"] = classify_tx_type(df)
    return df


def effective_credit_limit(balance_limit: float, manual_credit_limit: float) -> tuple[float | None, bool]:
    """Resolve the credit limit to use for utilisation: Plaid's value if present,
    otherwise the manually-entered fallback. Returns (limit, is_manual); limit is
    None when neither source has a value."""
    if pd.notna(balance_limit) and balance_limit > 0:
        return balance_limit, False
    if pd.notna(manual_credit_limit) and manual_credit_limit > 0:
        return manual_credit_limit, True
    return None, False
