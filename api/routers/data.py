"""Dashboard data endpoints for the React frontend: pre-shaped view models for the
Overview/Cash-flow/Budget/Anomalies/Ledger sections, plus the 5 write paths the
Streamlit dashboard exposes today (credit limit, budget, and the 3 ledger edits).

Reads compute view models server-side from `app/dashboard.py`'s already-tested pure
functions (via `api/viewmodels.py`) rather than exposing raw rows for the frontend
to interpret — see the R2 section of the migration plan. Writes are thin wrappers
around the existing `DatabaseClient` methods; no new DB logic lives here.

Every route requires a valid session (`CurrentUserDep`). Every write route
additionally requires `RequireCsrfDep` (api/deps.py::require_csrf).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel

from analytics.budget_periods import PERIOD_PATTERN
from analytics.categories import CANONICAL_CATEGORIES, canonicalize
from analytics.categorizer import merchant_key
from ingestion.plaid_ingestor import PlaidIngestor

from ..dataload import invalidate as invalidate_cache
from ..dataload import load_frames
from ..deps import CurrentUserDep, DbDep, RequireCsrfDep, SettingsDep
from ..filters import FiltersDep, apply_filters, build_filter_options
from ..viewmodels import (
    build_anomalies,
    build_budget,
    build_cash_flow,
    build_ledger,
    build_net_worth,
    build_overview,
    exclude_duplicate_rows,
    net_linked_transactions,
)

router = APIRouter(tags=["data"])


def _load(db: DbDep):
    return load_frames(db.database_url)


def _load_filtered(db: DbDep, filters: FiltersDep):
    """`(unfiltered, filtered, all_time, accounts)`.

    Enrichment happens once on the complete frame before any filtering — see
    `api/filters.py`, invariant 2 — so transfer pair matching sees both legs even when
    one leg's account is excluded. Callers pick the frame their section needs.
    """
    tx, acct_df = _load(db)
    filtered, all_time = apply_filters(tx, filters)
    return tx, filtered, all_time, acct_df


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class AssetMixItem(BaseModel):
    subtype_label: str
    balance: float


class OwnerAccountItem(BaseModel):
    account_name: str
    type: str
    value: float
    short_name: str


class OwnerBalanceItem(BaseModel):
    """One row per account HOLDER, not per account. Per-account detail lives in
    `accounts` for the chart tooltip — see PLAN.md Phase 15, Fix 4."""

    owner: str
    depository: float
    investment: float
    credit: float
    other: float
    net: float
    accounts: list[OwnerAccountItem]


class CreditUtilizationItem(BaseModel):
    account_key: str
    account_name: str
    owner_name: str | None
    current: float
    limit: float | None
    pct: float | None
    """Fraction of the limit used (0.42 = 42%), not percentage points."""
    is_manual: bool


class StaleAccountItem(BaseModel):
    """Sync health: `accounts.updated_at` is the last BALANCE REFRESH, not the last
    transaction. A gap here suggests a broken Plaid Item, not an unused account."""

    account_key: str
    account_name: str
    days_stale: int


class DormantAccountItem(BaseModel):
    """No transactions in `DORMANT_DAYS`, with a non-zero balance. Informational."""

    account_key: str
    account_name: str
    owner_name: str | None
    days_inactive: int
    balance: float


class NetWorth(BaseModel):
    net_worth: float
    total_assets: float
    total_liabilities: float
    asset_mix: list[AssetMixItem]
    owner_balances: list[OwnerBalanceItem]
    credit_utilization: list[CreditUtilizationItem]
    stale_accounts: list[StaleAccountItem]
    dormant_accounts: list[DormantAccountItem]
    forked_accounts: list[str]


class TopCategoryItem(BaseModel):
    category: str
    amount: float


class MonthOverMonthItem(BaseModel):
    """Wide row: one object per category carrying both months plus the "usual" baseline
    and drift context (Phase 23 folded the former Home tab's Category Drift card into
    this chart's data instead of shipping it separately). The long `{category, period,
    amount}` shape this used to be forced the frontend to pivot itself — moved
    server-side per this module's own "series are returned wide" rule."""

    category: str
    this_month: float
    last_month: float
    usual: float | None
    """The category's average monthly expense across complete months. None when there's
    no baseline history yet for this category."""
    this_month_drift_pct: float | None
    """Fraction: `(this_month - usual) / usual`, using a baseline that excludes the
    current (in-progress) month. None when `usual` isn't computable."""
    last_month_drift_pct: float | None
    """Fraction: `(last_month - usual) / usual`, using a baseline that additionally
    excludes last month itself from the average (so last month is never judged against
    a baseline partly made of itself) -- a DIFFERENT, slightly more accurate baseline
    than the `usual` value above, computed only for this percentage. None when not
    computable."""


class IncomeBreakdownItem(BaseModel):
    description: str
    amount: float


class SavingsRateTrendItem(BaseModel):
    month: str
    savings_rate: float | None
    """Fraction (0.2 = 20%). None when the month's income is below
    `MIN_MONTHLY_INCOME_FOR_RATE` — a month with no income has no meaningful rate,
    so the chart draws a gap rather than a spike. See PLAN.md Phase 15, Fix 2."""
    income: float
    expenses: float


class MetricSummary(BaseModel):
    """A headline figure plus the context needed to read it.

    Answers "is this normal for me?", which a bare number cannot. Whether a positive
    `delta_pct` is good or bad is deliberately NOT encoded here — that is polarity, and
    it belongs to the UI (`web/src/lib/polarity.ts`), because expenses rising and income
    rising are the same arithmetic and opposite news.
    """

    key: str
    value: float
    """The figure for the selected period."""
    baseline: float | None
    """The same quantity averaged over every complete month of history. None when there
    is not a single complete month to average."""
    delta_pct: float | None
    """Fraction: `(value - baseline) / abs(baseline)`. None when baseline is absent or
    zero. Divided by the ABSOLUTE baseline so the sign always means above/below."""
    baseline_months: int
    sparkline: list[float]
    comparison_kind: Literal["trailing_average", "last_period"]
    """Which comparison `baseline`/`delta_pct` represent: a trailing average across
    complete months (flows), or the value one period ago (balances). See
    `_build_metric`/`_build_last_period_metric` in `api/viewmodels.py`."""
    """Up to the last 12 complete months of the underlying monthly series."""


class Overview(BaseModel):
    income: float
    expenses: float
    net_flow: float
    savings_rate: float
    """Fraction (0.6 = 60%), not percentage points. See api/viewmodels.py."""
    flagged_count: int
    avg_weekly_expense: float
    avg_monthly_expense: float
    avg_weekly_income: float
    avg_monthly_income: float
    avg_monthly_net: float
    complete_months: int
    """How many whole calendar months the monthly averages above are computed over."""
    metrics: dict[str, MetricSummary]
    """Baseline/sparkline context, keyed by the field name it annotates."""
    top_categories: list[TopCategoryItem]
    month_over_month: list[MonthOverMonthItem]
    emergency_fund_months: float | None
    """Current value (liquid savings ÷ average monthly expenses), for the Emergency Fund
    card's meter. `net_worth_trend_monthly[*].emergency_fund_months` below is the
    historical trend version of the same idea -- the two use different baselines (this
    one an all-time average, the trend a rolling 6-month one) so they can legitimately
    show slightly different numbers for the current month; that's expected, not a bug."""
    income_breakdown: list[IncomeBreakdownItem]
    savings_rate_trend: list[SavingsRateTrendItem]
    # --- Former Home tab content (Phase 23) -----------------------------------------
    net_worth_trend_daily: list[NetWorthTrendDailyItem]
    net_worth_trend_monthly: list[NetWorthTrendMonthlyItem]
    net_worth_mom_delta: float | None
    """Latest net worth minus the closest snapshot at least one calendar month prior."""
    recurring_items: list[RecurringItem]
    top_merchants: list[MerchantItem]
    cash_flow_projection: CashFlowProjection | None
    biggest_expense_this_month: BiggestExpenseItem | None
    upcoming_recurring: list[UpcomingRecurringItem]


class OverviewResponse(BaseModel):
    net_worth: NetWorth
    overview: Overview


class CashFlowSeriesItem(BaseModel):
    """Wide row: one object per month carrying both series. The long
    `{month, tx_type, amount}` shape forced the frontend to pivot on the `tx_type`
    string, which it did case-incorrectly — see PLAN.md Phase 15, Fix 6."""

    month: str
    income: float
    expenses: float
    net: float


class WeeklyTrendItem(BaseModel):
    week: str
    income: float
    expenses: float
    net: float


class RollingSpendItem(BaseModel):
    date: str
    amount: float
    """Total spent in the 30 CALENDAR DAYS ending on `date`."""
    daily_avg: float
    """`amount / 30` — the per-day figure the old "Daily Spend" label implied."""


class MonthlyNetByOwnerItem(BaseModel):
    month: str
    owner: str
    amount: float


class CategoryDistributionItem(BaseModel):
    month: str
    category: str
    amount: float


class CashFlowResponse(BaseModel):
    income: float
    expenses: float
    net_flow: float
    transfer_count: int
    flagged_count: int
    savings_rate: float
    """Fraction (0.6 = 60%), not percentage points."""
    reimbursed: float
    """Total amount netted out of expenses this period via linked reimbursement pairs."""
    month_over_month: list[CashFlowSeriesItem]
    weekly_trend: list[WeeklyTrendItem]
    rolling_30d_spend: list[RollingSpendItem]
    monthly_net_by_owner: list[MonthlyNetByOwnerItem]
    category_distribution: list[CategoryDistributionItem]


class BudgetDetail(BaseModel):
    """One `pfc_detailed` value's spend inside a category, for the drill-down.
    `pfc_detailed` is None for rows Plaid never gave a detail for (seed data,
    manual corrections); those are kept rather than dropped so the parts sum to
    the category total."""

    pfc_detailed: str | None
    amount: float


class BudgetItem(BaseModel):
    category: str
    spent: float
    # None means "no budget set". 0.0 means "budgeted to spend nothing" -- a
    # real cap that any spend breaches. The UI must not collapse the two.
    limit: float | None
    pct: float | None
    is_over_budget: bool
    projected_eom: float | None
    is_current_month: bool
    # Phase 28: which month this row describes, and whether its cap was set
    # here or carried forward from an earlier month.
    period: str | None
    is_inherited: bool
    inherited_from: str | None
    details: list[BudgetDetail] = []


class BudgetResponse(BaseModel):
    month: str | None
    items: list[BudgetItem]


class NetWorthTrendDailyItem(BaseModel):
    date: str
    """ISO date, one snapshot per calendar day the pipeline actually ran
    (`account_balance_snapshots`) -- can be sparse if the pipeline hasn't run daily."""
    net_worth: float
    assets: float
    liabilities: float
    liquid_cash: float
    """Depository-only balance -- the subset of `assets` that excludes investments."""


class NetWorthTrendMonthlyItem(BaseModel):
    month: str
    """`YYYY-MM`. One row per calendar month, resampled from the last daily snapshot
    observed in that month."""
    net_worth: float
    savings_rate: float | None
    """Fraction (0.2 = 20%). None when the month's income was below the rate floor —
    see `SavingsRateTrendItem`."""
    credit_utilization_pct: float | None
    """Fraction: aggregate credit balance that month ÷ today's total credit limit.
    None when no account has a set limit."""
    emergency_fund_months: float | None
    """Liquid cash that month ÷ a trailing 6-month average expense as of that month.
    None until at least one month of expense history exists."""


class RecurringItem(BaseModel):
    description: str
    amount: float


class MerchantItem(BaseModel):
    description: str
    amount: float


class CashFlowProjection(BaseModel):
    month: str
    spent_so_far: float
    income_so_far: float
    projected_expenses: float
    projected_income: float
    days_elapsed: int
    days_in_month: int


class BiggestExpenseItem(BaseModel):
    description: str
    amount: float
    date: str


class UpcomingRecurringItem(BaseModel):
    description: str
    amount: float
    next_expected_date: str
    """A projection (a detected stream's predicted next date, or -- with no
    streams yet -- last occurrence plus the median inter-occurrence interval),
    not a confirmed billing date; the frontend hedges its copy accordingly."""
    typical_interval_days: int | None = None
    # Phase 31. `early_detection` marks a stream with fewer than three
    # occurrences, which the UI shows as lower confidence rather than asserting
    # it. None on the legacy median-gap fallback, which has no such notion.
    status: str | None = None
    stream_id: str | None = None


class LedgerItem(BaseModel):
    hash: str
    date: str
    owner_name: str | None
    account_name: str
    description: str
    amount: float
    category: str | None
    tx_type: str
    is_recurring: bool
    is_duplicate: bool
    pfc_detailed: str | None
    category_source: str | None
    linked_transaction_hash: str | None
    # Phase 31. When set, this row belongs to a detected recurring series and
    # its recurring control toggles the WHOLE series; when null the control is
    # per-row. Two different consequences, so the UI must show which before the
    # click, not after.
    stream_id: str | None = None
    stream_description: str | None = None


class LedgerResponse(BaseModel):
    transactions: list[LedgerItem]


class AnomalyItem(BaseModel):
    """Phase 34. Replaces the per-transaction outlier row: an anomaly is now
    per-category-per-month (drift) or per-stream (price creep), and carries the
    sentence it was derived from rather than an unexplainable score."""

    kind: str          # category_drift | price_creep
    subject: str       # category name, or stream_id
    period: str        # 'YYYY-MM'
    severity: str      # medium | high
    explanation: str
    detected_at: str | None = None


class AnomaliesResponse(BaseModel):
    anomalies: list[AnomalyItem]


class AnomalyDismissal(BaseModel):
    kind: str
    subject: str
    period: str


class CategoriesResponse(BaseModel):
    categories: list[str]


class MonthOption(BaseModel):
    key: str
    """`YYYY-MM`, the value the `months` query param expects."""
    label: str
    """Human-readable, e.g. "July 2026"."""


class FilterOptionsResponse(BaseModel):
    owners: list[str]
    categories: list[str]
    accounts: list[str]
    months: list[MonthOption]
    amount_min: float
    amount_max: float


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------


@router.get("/overview", response_model=OverviewResponse)
def get_overview(current_user: CurrentUserDep, db: DbDep, filters: FiltersDep) -> OverviewResponse:
    tx, filtered, all_time, acct_df = _load_filtered(db, filters)
    return OverviewResponse(
        # `tx` (unfiltered) not `filtered`: dormancy is about real history, and neither
        # the duplicate flag nor the period filter bears on when an account last saw use.
        net_worth=NetWorth(**build_net_worth(acct_df, tx)),
        overview=Overview(
            **build_overview(
                net_linked_transactions(exclude_duplicate_rows(filtered)),
                acct_df,
                net_linked_transactions(exclude_duplicate_rows(all_time)),
                # `all_time` (not `filtered`): every former-Home insight compares against
                # the user's own full history, same reasoning the rest of this frame's
                # baselines use -- a status surface that changed shape under an active
                # period filter would defeat its own purpose (Phase 23).
                db.get_net_worth_history(),
                # Phase 31: detected streams drive Upcoming Recurring Charges when any
                # exist. Each stream is already one deduplicated charge, so the card
                # stops listing the same bill under near-identical descriptions.
                db.get_recurring_streams(),
            )
        ),
    )


@router.get("/cash-flow", response_model=CashFlowResponse)
def get_cash_flow(current_user: CurrentUserDep, db: DbDep, filters: FiltersDep) -> CashFlowResponse:
    _tx, filtered, _all_time, _acct_df = _load_filtered(db, filters)
    return CashFlowResponse(**build_cash_flow(net_linked_transactions(exclude_duplicate_rows(filtered))))


@router.get("/budget", response_model=BudgetResponse)
def get_budget(
    current_user: CurrentUserDep,
    db: DbDep,
    filters: FiltersDep,
    month: str | None = Query(
        None,
        description="Month to budget, 'YYYY-MM'. Defaults to the latest month in the filtered data.",
    ),
) -> BudgetResponse:
    """The budget month is `month`, NOT `period`: the filter bar already owns
    `period` as a query parameter and its values are presets ('all_time',
    'last_3_months'). A second `period` meaning 'YYYY-MM' would shadow it and
    make every filtered budget request a 422. The storage column and the domain
    term stay `period`; only the HTTP name differs, and only because of that."""
    if month is not None and not PERIOD_PATTERN.match(month):
        raise HTTPException(status_code=422, detail="month must be 'YYYY-MM'")
    _tx, filtered, _all_time, _acct_df = _load_filtered(db, filters)
    return BudgetResponse(
        **build_budget(
            net_linked_transactions(exclude_duplicate_rows(filtered)),
            db.get_budget_periods(),
            period=month,
        )
    )


@router.get("/ledger", response_model=LedgerResponse)
def get_ledger(current_user: CurrentUserDep, db: DbDep, filters: FiltersDep) -> LedgerResponse:
    _tx, filtered, _all_time, _acct_df = _load_filtered(db, filters)
    # Duplicate-flagged rows stay: the ledger checkbox is the only way to un-flag one.
    return LedgerResponse(
        transactions=[
            LedgerItem(**item) for item in build_ledger(filtered, db.get_recurring_streams())
        ]
    )


@router.get("/anomalies", response_model=AnomaliesResponse)
def get_anomalies(
    current_user: CurrentUserDep,
    db: DbDep,
    month: str | None = Query(None, description="Limit to one month, 'YYYY-MM'."),
) -> AnomaliesResponse:
    """Reads the `anomalies` table rather than deriving per-transaction outliers.
    Dismissed anomalies are excluded by the query itself. Takes no transaction
    filters: an anomaly is a statement about a category or a stream over a
    period, so narrowing the ledger view does not change whether it holds."""
    if month is not None and not PERIOD_PATTERN.match(month):
        raise HTTPException(status_code=422, detail="month must be 'YYYY-MM'")
    return AnomaliesResponse(
        anomalies=[AnomalyItem(**item) for item in db.get_anomalies(month)]
    )


@router.post("/anomalies/dismiss", status_code=status.HTTP_204_NO_CONTENT)
def dismiss_anomaly(
    body: AnomalyDismissal,
    current_user: CurrentUserDep,
    _csrf: RequireCsrfDep,
    db: DbDep,
) -> Response:
    """Dismiss one anomaly for one period. Deliberately period-scoped: dismissing
    September's Dining drift must not silence October's."""
    db.dismiss_anomaly(body.kind, body.subject, body.period)
    invalidate_cache(db.database_url)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/anomalies/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_anomaly(
    body: AnomalyDismissal,
    current_user: CurrentUserDep,
    _csrf: RequireCsrfDep,
    db: DbDep,
) -> Response:
    """Undo a dismissal, so a mis-click is recoverable."""
    db.restore_anomaly(body.kind, body.subject, body.period)
    invalidate_cache(db.database_url)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/filter-options", response_model=FilterOptionsResponse)
def get_filter_options(current_user: CurrentUserDep, db: DbDep) -> FilterOptionsResponse:
    """Options for the filter UI, derived from the UNFILTERED frame so the lists don't
    shrink out from under the user as they narrow the view."""
    tx, _acct_df = _load(db)
    return FilterOptionsResponse(**build_filter_options(tx))


@router.get("/categories", response_model=CategoriesResponse)
def get_categories(current_user: CurrentUserDep, db: DbDep) -> CategoriesResponse:
    return CategoriesResponse(categories=db.get_categories())


# ---------------------------------------------------------------------------
# Write endpoints — request models
# ---------------------------------------------------------------------------


class CreditLimitUpdate(BaseModel):
    limit: float | None


class BudgetUpdate(BaseModel):
    monthly_limit: float
    # Which month this cap applies from. Omitted means the current calendar
    # month -- never "all months", since that is precisely the flat-table
    # behaviour Phase 28 replaced. Named `month` to match the query parameter
    # on GET /budget; see the note there on why it cannot be called `period`.
    month: str | None = None


class CategoryUpdate(BaseModel):
    category: str


class CategoryUpdateResponse(BaseModel):
    backfilled_count: int


class RecurringUpdate(BaseModel):
    recurring: bool


class DuplicateUpdate(BaseModel):
    duplicate: bool


class LinkTransactionRequest(BaseModel):
    other_hash: str


# ---------------------------------------------------------------------------
# Write endpoints
# ---------------------------------------------------------------------------


@router.patch("/accounts/{account_key}/credit-limit", status_code=status.HTTP_204_NO_CONTENT)
def update_credit_limit(
    account_key: str,
    body: CreditLimitUpdate,
    current_user: CurrentUserDep,
    _csrf: RequireCsrfDep,
    db: DbDep,
) -> Response:
    db.set_manual_credit_limit(account_key, body.limit)
    invalidate_cache(db.database_url)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/budgets/{category}", status_code=status.HTTP_204_NO_CONTENT)
def update_budget(
    category: str,
    body: BudgetUpdate,
    current_user: CurrentUserDep,
    _csrf: RequireCsrfDep,
    db: DbDep,
) -> Response:
    """Set one category's cap for one month. Other months are untouched; they
    keep whatever they inherit. Writes only `budget_periods` — the legacy
    `budgets` table belongs to the frozen Streamlit dashboard, which writes it
    itself, so touching it here would discard budgets saved from there."""
    month = body.month or date.today().strftime("%Y-%m")
    if not PERIOD_PATTERN.match(month):
        raise HTTPException(status_code=422, detail="month must be 'YYYY-MM'")
    db.upsert_budget_period(category, month, body.monthly_limit)
    invalidate_cache(db.database_url)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/budgets/{category}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(
    category: str,
    current_user: CurrentUserDep,
    _csrf: RequireCsrfDep,
    db: DbDep,
    month: str | None = Query(None, description="Month to clear, 'YYYY-MM'."),
) -> Response:
    """Clear one month's explicit cap. The month then falls back to *inheriting*
    the most recent earlier cap — which is not the same as being capped at 0."""
    resolved = month or date.today().strftime("%Y-%m")
    if not PERIOD_PATTERN.match(resolved):
        raise HTTPException(status_code=422, detail="month must be 'YYYY-MM'")
    db.delete_budget_period(category, resolved)
    invalidate_cache(db.database_url)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/transactions/{transaction_hash}/category", response_model=CategoryUpdateResponse)
def update_transaction_category(
    transaction_hash: str,
    body: CategoryUpdate,
    current_user: CurrentUserDep,
    _csrf: RequireCsrfDep,
    db: DbDep,
) -> CategoryUpdateResponse:
    """The category set is closed (Phase 28c). This endpoint previously took
    arbitrary free text, so budget caps -- which are keyed on category -- could
    be orphaned by a typo and the category list grew without bound.

    Input is normalised rather than merely rejected: 'Dining' and
    'food and drink' both store FOOD_AND_DRINK. Only a value that cannot be
    mapped *unambiguously* is refused, because guessing would silently rewrite
    what the user meant."""
    category = canonicalize(body.category)
    if category is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown category {body.category!r}. "
                f"Expected one of: {', '.join(CANONICAL_CATEGORIES)}"
            ),
        )
    fields = db.get_transaction_merchant_fields(transaction_hash)
    key = merchant_key(fields[0], fields[1]) if fields else None
    backfilled_count = db.update_transaction_category(transaction_hash, category, key or None)
    invalidate_cache(db.database_url)
    return CategoryUpdateResponse(backfilled_count=backfilled_count)


class StreamRecurringUpdate(BaseModel):
    recurring: bool


class StreamRecurringResponse(BaseModel):
    updated_count: int


@router.patch("/streams/{stream_id}/recurring", response_model=StreamRecurringResponse)
def update_stream_recurring(
    stream_id: str,
    body: StreamRecurringUpdate,
    current_user: CurrentUserDep,
    _csrf: RequireCsrfDep,
    db: DbDep,
) -> StreamRecurringResponse:
    """Toggle recurring for a whole detected stream (Phase 31).

    The per-row endpoint below still exists for transactions that belong to no
    stream. This one fixes "the same charge can be checked recurring over and
    over": the flag is per-row, so every occurrence was independently checkable
    and Upcoming then listed near-duplicates."""
    updated = db.update_recurring_for_stream(stream_id, body.recurring)
    invalidate_cache(db.database_url)
    return StreamRecurringResponse(updated_count=updated)


@router.patch("/transactions/{transaction_hash}/recurring", status_code=status.HTTP_204_NO_CONTENT)
def update_transaction_recurring(
    transaction_hash: str,
    body: RecurringUpdate,
    current_user: CurrentUserDep,
    _csrf: RequireCsrfDep,
    db: DbDep,
) -> Response:
    db.update_transaction_recurring(transaction_hash, body.recurring)
    invalidate_cache(db.database_url)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/transactions/{transaction_hash}/duplicate", status_code=status.HTTP_204_NO_CONTENT)
def update_transaction_duplicate(
    transaction_hash: str,
    body: DuplicateUpdate,
    current_user: CurrentUserDep,
    _csrf: RequireCsrfDep,
    db: DbDep,
) -> Response:
    db.update_transaction_duplicate(transaction_hash, body.duplicate)
    invalidate_cache(db.database_url)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/transactions/{transaction_hash}/link", status_code=status.HTTP_204_NO_CONTENT)
def link_transaction(
    transaction_hash: str,
    body: LinkTransactionRequest,
    current_user: CurrentUserDep,
    _csrf: RequireCsrfDep,
    db: DbDep,
) -> Response:
    try:
        db.link_transactions(transaction_hash, body.other_hash)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    invalidate_cache(db.database_url)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/transactions/{transaction_hash}/link", status_code=status.HTTP_204_NO_CONTENT)
def unlink_transaction(
    transaction_hash: str,
    current_user: CurrentUserDep,
    _csrf: RequireCsrfDep,
    db: DbDep,
) -> Response:
    db.unlink_transaction(transaction_hash)
    invalidate_cache(db.database_url)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class BalanceRefreshResponse(BaseModel):
    accounts_refreshed: int
    accounts_failed: int


@router.post("/accounts/refresh-balances", response_model=BalanceRefreshResponse)
def refresh_balances(
    current_user: CurrentUserDep,
    _csrf: RequireCsrfDep,
    db: DbDep,
    settings: SettingsDep,
) -> BalanceRefreshResponse:
    """Fetch live balances on demand (Phase 35).

    Without this, balances are only as fresh as the last pipeline run -- up to
    24 hours stale -- which makes goal progress and net worth read as wrong
    right after money moves. `/accounts/balance/get` needs no re-link.

    A partial failure is reported, not raised: one broken Plaid Item should not
    stop the other two from refreshing.
    """
    if not settings.plaid_client_id or not settings.plaid_secret:
        raise HTTPException(status_code=503, detail="Plaid credentials are not configured")
    if not settings.plaid_access_tokens:
        raise HTTPException(status_code=503, detail="No Plaid access tokens are configured")

    ingestor = PlaidIngestor(
        client_id=settings.plaid_client_id,
        secret=settings.plaid_secret,
        access_tokens=settings.plaid_access_tokens,
        base_url=settings.plaid_base_url,
    )
    owner_by_token = dict(
        zip(settings.plaid_access_tokens, settings.plaid_access_token_owners, strict=False)
    )
    accounts, failed = ingestor.refresh_balances(owner_by_token)

    for account in accounts:
        account.pop("_token_fingerprint", None)
    if accounts:
        key_remap = db.canonicalize_account_keys(accounts)
        for account in accounts:
            account["account_key"] = key_remap.get(account["account_key"], account["account_key"])
        db.upsert_plaid_accounts(accounts)
        # Upserts today's row in place rather than adding a second one --
        # account_balance_snapshots is UNIQUE (account_key, snapshot_date).
        db.record_balance_snapshots(accounts)

    invalidate_cache(db.database_url)
    return BalanceRefreshResponse(accounts_refreshed=len(accounts), accounts_failed=len(failed))
