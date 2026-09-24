"""The canonical category set, and conservative normalisation onto it.

`update_transaction_category` historically accepted arbitrary free text with no
validation, so the effective category set was the 18 canonical names *plus
every string anyone had ever typed*. That is tolerable while categories are
only a label, but Phase 28 keys budget caps on them: an open set means a typo
creates a permanent orphan budget row and the category list grows without
bound.

The names mirror `database/migrations/023_pfc_taxonomy.sql` — Plaid's
`personal_finance_category` primary values, plus OTHER and UNCATEGORIZED.

`canonicalize` is deliberately **conservative**. It normalises case, spacing
and the known Phase-1 legacy names from migration 024, and returns None for
anything else. It does no fuzzy matching and never falls back to OTHER: this
function's output can rewrite a correction the user made by hand, and a wrong
guess silently destroys what they meant. Returning None lets the caller report
the value and leave it alone, which is always recoverable.
"""

from __future__ import annotations

__all__ = [
    "CANONICAL_CATEGORIES",
    "LEGACY_CATEGORY_MAP",
    "canonicalize",
    "is_canonical",
]

#: Must stay in sync with migration 023's INSERT.
CANONICAL_CATEGORIES: tuple[str, ...] = (
    "BANK_FEES",
    "ENTERTAINMENT",
    "FOOD_AND_DRINK",
    "GENERAL_MERCHANDISE",
    "GENERAL_SERVICES",
    "GOVERNMENT_AND_NON_PROFIT",
    "HOME_IMPROVEMENT",
    "INCOME",
    "LOAN_PAYMENTS",
    "MEDICAL",
    "OTHER",
    "PERSONAL_CARE",
    "RENT_AND_UTILITIES",
    "TRANSFER_IN",
    "TRANSFER_OUT",
    "TRANSPORTATION",
    "TRAVEL",
    "UNCATEGORIZED",
)

_CANONICAL_SET = frozenset(CANONICAL_CATEGORIES)

#: The Phase-1 names migration 024 retired, each mapped to its nearest
#: canonical equivalent. Every entry is a judgement made once, in the open,
#: rather than inferred at runtime.
#:
#: Two are worth explaining:
#:  - 'ATM' -> TRANSFER_OUT: a cash withdrawal moves money out of the account;
#:    Plaid's taxonomy has no ATM primary.
#:  - 'Savings' -> TRANSFER_IN: a transfer to savings is an inflow to the
#:    saving account, which is how the rest of the pipeline already treats it.
LEGACY_CATEGORY_MAP: dict[str, str] = {
    "ATM": "TRANSFER_OUT",
    "DINING": "FOOD_AND_DRINK",
    "ENTERTAINMENT": "ENTERTAINMENT",
    "GROCERIES": "FOOD_AND_DRINK",
    "HEALTH": "MEDICAL",
    "HOUSING": "RENT_AND_UTILITIES",
    "INCOME": "INCOME",
    "SAVINGS": "TRANSFER_IN",
    "SHOPPING": "GENERAL_MERCHANDISE",
    "SUBSCRIPTIONS": "GENERAL_SERVICES",
    "TRANSFER": "TRANSFER_OUT",
    "TRANSPORT": "TRANSPORTATION",
    "TRAVEL": "TRAVEL",
    "UTILITIES": "RENT_AND_UTILITIES",
}


def is_canonical(value: str | None) -> bool:
    """Whether `value` is exactly one of the canonical names."""
    return value in _CANONICAL_SET


def canonicalize(value: str | None) -> str | None:
    """Map `value` onto a canonical category, or None if it cannot be mapped
    **unambiguously**.

    Handles, in order: exact match; case and surrounding whitespace; internal
    spaces or hyphens standing in for underscores; the known legacy names.

    Returns None for anything else — including near misses. Callers should
    report an unmapped value and leave the underlying row untouched.
    """
    if value is None:
        return None

    stripped = value.strip()
    if not stripped:
        return None

    if stripped in _CANONICAL_SET:
        return stripped

    normalized = stripped.upper().replace(" ", "_").replace("-", "_")
    while "__" in normalized:
        normalized = normalized.replace("__", "_")

    if normalized in _CANONICAL_SET:
        return normalized

    return LEGACY_CATEGORY_MAP.get(normalized)
