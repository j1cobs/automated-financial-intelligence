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

from app.dashboard import load_financial_data

from ..deps import CurrentUserDep, DbDep, RequireCsrfDep
from ..viewmodels import (
    build_anomalies,
    build_budget,
    build_cash_flow,
    build_ledger,
    build_net_worth,
    build_overview,
    exclude_duplicate_rows,
    prepare_transactions,
)

router = APIRouter(tags=["data"])


def _load(db: DbDep):
    tx_df, acct_df = load_financial_data(db.database_url)
    return prepare_transactions(tx_df), acct_df


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class AssetMixItem(BaseModel):
    subtype_label: str
    balance: float


class OwnerBalanceItem(BaseModel):
    owner: str
    value: float
    type: str


class CreditUtilizationItem(BaseModel):
    account_name: str
    owner_name: str | None
    current: float
    limit: float | None
    pct: float | None
    is_manual: bool


class StaleAccountItem(BaseModel):
    account_name: str
    days_stale: int


class NetWorth(BaseModel):
    net_worth: float
    total_assets: float
    total_liabilities: float
    asset_mix: list[AssetMixItem]
    owner_balances: list[OwnerBalanceItem]
    credit_utilization: list[CreditUtilizationItem]
    stale_accounts: list[StaleAccountItem]
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
    savings_rate: float


class Overview(BaseModel):
    income: float
    expenses: float
    net_flow: float
    savings_rate: float
    flagged_count: int
    avg_weekly_expense: float
    avg_monthly_expense: float
    avg_weekly_income: float
    avg_monthly_income: float
    top_categories: list[TopCategoryItem]
    month_over_month: list[MonthOverMonthItem]
    emergency_fund_months: float | None
    income_breakdown: list[IncomeBreakdownItem]
    savings_rate_trend: list[SavingsRateTrendItem]


class OverviewResponse(BaseModel):
    net_worth: NetWorth
    overview: Overview


class CashFlowSeriesItem(BaseModel):
    month: str
    tx_type: str
    amount: float


class WeeklyTrendItem(BaseModel):
    week: str
    tx_type: str
    amount: float


class RollingSpendItem(BaseModel):
    date: str
    amount: float


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


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------


@router.get("/overview", response_model=OverviewResponse)
def get_overview(current_user: CurrentUserDep, db: DbDep) -> OverviewResponse:
    tx, acct_df = _load(db)
    real = exclude_duplicate_rows(tx)
    return OverviewResponse(
        net_worth=NetWorth(**build_net_worth(acct_df)),
        overview=Overview(**build_overview(real, acct_df)),
    )


@router.get("/cash-flow", response_model=CashFlowResponse)
def get_cash_flow(current_user: CurrentUserDep, db: DbDep) -> CashFlowResponse:
    tx, _acct_df = _load(db)
    real = exclude_duplicate_rows(tx)
    return CashFlowResponse(**build_cash_flow(real))


@router.get("/budget", response_model=BudgetResponse)
def get_budget(current_user: CurrentUserDep, db: DbDep) -> BudgetResponse:
    tx, _acct_df = _load(db)
    real = exclude_duplicate_rows(tx)
    budget_rows = db.get_budgets()
    return BudgetResponse(**build_budget(real, budget_rows))


@router.get("/ledger", response_model=LedgerResponse)
def get_ledger(current_user: CurrentUserDep, db: DbDep) -> LedgerResponse:
    tx, _acct_df = _load(db)
    return LedgerResponse(transactions=[LedgerItem(**item) for item in build_ledger(tx)])


@router.get("/anomalies", response_model=AnomaliesResponse)
def get_anomalies(current_user: CurrentUserDep, db: DbDep) -> AnomaliesResponse:
    tx, _acct_df = _load(db)
    real = exclude_duplicate_rows(tx)
    return AnomaliesResponse(anomalies=[AnomalyItem(**item) for item in build_anomalies(real)])


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
    return Response(status_code=status.HTTP_204_NO_CONTENT)
