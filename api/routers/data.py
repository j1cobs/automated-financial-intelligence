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

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from ..dataload import invalidate as invalidate_cache
from ..dataload import load_frames
from ..deps import CurrentUserDep, DbDep, RequireCsrfDep
from ..filters import FiltersDep, apply_filters, build_filter_options
from ..viewmodels import (
    build_anomalies,
    build_budget,
    build_cash_flow,
    build_home,
    build_ledger,
    build_net_worth,
    build_overview,
    exclude_duplicate_rows,
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
    category: str
    period: str
    amount: float


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
    income_breakdown: list[IncomeBreakdownItem]
    savings_rate_trend: list[SavingsRateTrendItem]


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
    month_over_month: list[CashFlowSeriesItem]
    weekly_trend: list[WeeklyTrendItem]
    rolling_30d_spend: list[RollingSpendItem]
    monthly_net_by_owner: list[MonthlyNetByOwnerItem]
    category_distribution: list[CategoryDistributionItem]


class BudgetItem(BaseModel):
    category: str
    spent: float
    limit: float | None
    pct: float | None
    is_over_budget: bool
    projected_eom: float | None
    is_current_month: bool


class BudgetResponse(BaseModel):
    month: str | None
    items: list[BudgetItem]


class NetWorthTrendItem(BaseModel):
    date: str
    """ISO date, one snapshot per calendar day (`account_balance_snapshots`)."""
    net_worth: float


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


class CategoryDriftItem(BaseModel):
    category: str
    current: float
    baseline: float
    """The category's own historical average over complete months, not a budget."""
    drift_pct: float
    """Fraction: `(current - baseline) / baseline`. Positive = spending more than usual."""


class SubscriptionItem(BaseModel):
    description: str
    average_amount: float
    months_seen: int
    """Out of the trailing 6 months."""


class HomeResponse(BaseModel):
    net_worth_trend: list[NetWorthTrendItem]
    recurring_monthly_spend: float
    recurring_items: list[RecurringItem]
    top_merchants: list[MerchantItem]
    cash_flow_projection: CashFlowProjection | None
    category_drift: list[CategoryDriftItem]
    subscriptions: list[SubscriptionItem]


class LedgerItem(BaseModel):
    hash: str
    date: str
    owner_name: str | None
    account_name: str
    description: str
    amount: float
    category: str | None
    is_recurring: bool
    is_duplicate: bool


class LedgerResponse(BaseModel):
    transactions: list[LedgerItem]


class AnomalyItem(BaseModel):
    date: str
    owner_name: str | None
    account_name: str
    description: str
    amount: float
    category: str | None
    outlier_score: float


class AnomaliesResponse(BaseModel):
    anomalies: list[AnomalyItem]


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
                exclude_duplicate_rows(filtered),
                acct_df,
                exclude_duplicate_rows(all_time),
            )
        ),
    )


@router.get("/home", response_model=HomeResponse)
def get_home(current_user: CurrentUserDep, db: DbDep, filters: FiltersDep) -> HomeResponse:
    # `all_time` (not `filtered`): every Home insight compares against the user's own
    # full history, same reasoning `build_overview`'s baselines use -- a status page
    # that changes shape under an active period filter would defeat its own purpose.
    _tx, _filtered, all_time, _acct_df = _load_filtered(db, filters)
    return HomeResponse(**build_home(exclude_duplicate_rows(all_time), db.get_net_worth_history()))


@router.get("/cash-flow", response_model=CashFlowResponse)
def get_cash_flow(current_user: CurrentUserDep, db: DbDep, filters: FiltersDep) -> CashFlowResponse:
    _tx, filtered, _all_time, _acct_df = _load_filtered(db, filters)
    return CashFlowResponse(**build_cash_flow(exclude_duplicate_rows(filtered)))


@router.get("/budget", response_model=BudgetResponse)
def get_budget(current_user: CurrentUserDep, db: DbDep, filters: FiltersDep) -> BudgetResponse:
    _tx, filtered, _all_time, _acct_df = _load_filtered(db, filters)
    return BudgetResponse(**build_budget(exclude_duplicate_rows(filtered), db.get_budgets()))


@router.get("/ledger", response_model=LedgerResponse)
def get_ledger(current_user: CurrentUserDep, db: DbDep, filters: FiltersDep) -> LedgerResponse:
    _tx, filtered, _all_time, _acct_df = _load_filtered(db, filters)
    # Duplicate-flagged rows stay: the ledger checkbox is the only way to un-flag one.
    return LedgerResponse(transactions=[LedgerItem(**item) for item in build_ledger(filtered)])


@router.get("/anomalies", response_model=AnomaliesResponse)
def get_anomalies(current_user: CurrentUserDep, db: DbDep, filters: FiltersDep) -> AnomaliesResponse:
    _tx, filtered, _all_time, _acct_df = _load_filtered(db, filters)
    return AnomaliesResponse(
        anomalies=[AnomalyItem(**item) for item in build_anomalies(exclude_duplicate_rows(filtered))]
    )


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


class CategoryUpdate(BaseModel):
    category: str


class RecurringUpdate(BaseModel):
    recurring: bool


class DuplicateUpdate(BaseModel):
    duplicate: bool


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
    db.upsert_budget(category, body.monthly_limit)
    invalidate_cache(db.database_url)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/transactions/{transaction_hash}/category", status_code=status.HTTP_204_NO_CONTENT)
def update_transaction_category(
    transaction_hash: str,
    body: CategoryUpdate,
    current_user: CurrentUserDep,
    _csrf: RequireCsrfDep,
    db: DbDep,
) -> Response:
    db.update_transaction_category(transaction_hash, body.category)
    invalidate_cache(db.database_url)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
