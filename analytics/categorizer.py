from __future__ import annotations

import re

import pandas as pd

# Trailing "Purchase /" (or "Purchase/") prefix Plaid/the bank sometimes prepends to a raw
# description, e.g. "Purchase /CAFE DU PARQUET".
_PURCHASE_PREFIX_RE = re.compile(r"^PURCHASE\s*/\s*", re.IGNORECASE)

# A trailing "<one word> <province/territory code>" tail, e.g. "MONTREAL QC", "TORONTO ON",
# "QUEBEC QC". The city token is deliberately general (not a hardcoded city list) so it
# generalizes past the merchants seen in the Step 0 probe, and deliberately restricted to
# exactly one trailing word before the code: a merchant name is itself frequently multiple
# words (e.g. "CAFE DU PARQUET"), and matching an unbounded run of trailing words is ambiguous
# about where the merchant name ends and the city begins — it would strip "DU PARQUET
# MONTREAL QC" instead of just "MONTREAL QC". Per the under-merging bias documented on
# `merchant_key`, a multi-word city (rare) is left un-stripped rather than risk eating into
# the merchant name.
#
# The trailing code itself is NOT general — it is pinned to Canada's 13 real province/
# territory abbreviations, not any 2-letter string. Every account behind this pipeline is
# Canadian (Desjardins/BNC), so no other 2-letter code is a legitimate location suffix here.
# An unrestricted `[A-Z]{2}` matched the last two letters of any multi-word merchant name that
# happens to end that way (e.g. "Uber Eats US" -> "UBER", eating "EATS US" as if it were a
# city+province) — exactly the over-merging this normalizer is designed to avoid.
_CANADIAN_PROVINCE_CODES = (
    "AB",
    "BC",
    "MB",
    "NB",
    "NL",
    "NS",
    "NT",
    "NU",
    "ON",
    "PE",
    "QC",
    "SK",
    "YT",
)
_TRAILING_CITY_PROVINCE_RE = re.compile(
    r"\s+[A-Z][A-Z'.-]*\s+(?:" + "|".join(_CANADIAN_PROVINCE_CODES) + r")$"
)

# A trailing pure numeric store-number token, e.g. "METRO #4521" -> "#4521" or "METRO 4521".
_TRAILING_STORE_NUMBER_RE = re.compile(r"\s+#?\d+$")

_WHITESPACE_RE = re.compile(r"\s+")


def merchant_key(merchant_name: str | None, description: str) -> str:
    """Normalize a merchant identity to a stable lookup key for merchant_categories.

    Prefers `merchant_name` (Plaid-cleaned) when present and non-empty; falls back to
    `description` otherwise — confirmed by the Step 0 probe to be routine traffic (~29% of
    rows), not an edge case. The value is uppercased, a leading "Purchase /" prefix is
    stripped, a trailing "<city/words> <2-letter province code>" tail is stripped, a trailing
    pure numeric store-number token is stripped, and repeated whitespace is collapsed.

    Bias: prefer UNDER-merging over OVER-merging. Two keys for what is really one merchant
    just costs the user a second, harmless correction (merchant memory converges after both
    are made). One key that falsely conflates two different real merchants silently corrupts
    a category for one of them, and nothing surfaces that mistake to the user. So every strip
    rule here targets patterns that are clearly location/transaction-type noise, not general
    trailing tokens that might be part of a genuine merchant name.
    """
    raw = merchant_name if merchant_name else description
    if not raw:
        return ""

    key = raw.upper()
    key = _PURCHASE_PREFIX_RE.sub("", key)
    key = _TRAILING_CITY_PROVINCE_RE.sub("", key)
    key = _TRAILING_STORE_NUMBER_RE.sub("", key)
    key = _WHITESPACE_RE.sub(" ", key).strip()
    return key


class CascadeCategorizer:
    """Assigns `category` / `category_source` via a merchant-memory-first cascade.

    Sibling to `analytics/classifier.py` (TF-IDF, not wired yet) and
    `analytics/placeholders.py` (the stubbed bundle this replaces when
    `CATEGORIZER_MODE` selects it). This module does no I/O: `merchant_lookup` is a plain
    dict the caller (`pipeline/runner.py`, in a later wave) pre-fetches from
    `database.db.DatabaseClient` — `analytics/` must not import `database/` (see CLAUDE.md's
    layering rule).
    """

    def categorize(
        self, frame: pd.DataFrame, merchant_lookup: dict[str, str]
    ) -> pd.DataFrame:
        """Returns a copy of `frame` with `category` and `category_source` columns set.

        Resolution order per row, first hit wins:
        1. Merchant memory — `merchant_lookup[merchant_key(merchant_name, description)]`.
           -> category_source = "merchant"
        2. Plaid PFC primary — `row["pfc_primary"]`, when present/non-empty.
           -> category_source = "plaid"
        3. Fallback -> category = "UNCATEGORIZED", category_source = "none"

        Missing `merchant_name` / `description` / `pfc_primary` columns (e.g. an empty frame
        shaped only by `_NORMALIZED_COLUMNS`, or a future non-Plaid source with none of these
        fields) are treated as every value being absent for that column, landing rows on the
        fallback layer rather than raising KeyError.
        """
        result = frame.copy()

        n = len(result)
        merchant_names = (
            result["merchant_name"]
            if "merchant_name" in result.columns
            else pd.Series([None] * n, index=result.index)
        )
        descriptions = (
            result["description"]
            if "description" in result.columns
            else pd.Series([None] * n, index=result.index)
        )
        pfc_primaries = (
            result["pfc_primary"]
            if "pfc_primary" in result.columns
            else pd.Series([None] * n, index=result.index)
        )

        def _resolve(merchant_name, description, pfc_primary) -> tuple[str, str]:
            key = merchant_key(
                merchant_name if pd.notna(merchant_name) else None,
                description if pd.notna(description) else "",
            )
            if key and key in merchant_lookup:
                return merchant_lookup[key], "merchant"
            if pd.notna(pfc_primary) and str(pfc_primary).strip():
                return str(pfc_primary), "plaid"
            return "UNCATEGORIZED", "none"

        resolved = [
            _resolve(mn, desc, pfc)
            for mn, desc, pfc in zip(
                merchant_names, descriptions, pfc_primaries, strict=True
            )
        ]

        if resolved:
            categories, sources = zip(*resolved, strict=True)
        else:
            categories, sources = (), ()

        result["category"] = pd.Series(categories, index=result.index, dtype="object")
        result["category_source"] = pd.Series(
            sources, index=result.index, dtype="object"
        )
        return result
