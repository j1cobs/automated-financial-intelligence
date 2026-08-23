/**
 * TypeScript mirrors of the Pydantic response models in `api/routers/data.py`.
 * Field names/shapes must match exactly — these are what the FastAPI backend
 * actually serializes, not a reinterpretation. See `api/viewmodels.py` for
 * the business logic that produces these shapes.
 */

// ---------------------------------------------------------------------------
// GET /overview
// ---------------------------------------------------------------------------

export interface AssetMixItem {
  subtype_label: string;
  balance: number;
}

export interface OwnerBalanceItem {
  owner: string;
  value: number;
  type: string;
}

export interface CreditUtilizationItem {
  account_name: string;
  owner_name: string | null;
  current: number;
  limit: number | null;
  pct: number | null;
  is_manual: boolean;
}

export interface StaleAccountItem {
  account_name: string;
  days_stale: number;
}

export interface NetWorth {
  net_worth: number;
  total_assets: number;
  total_liabilities: number;
  asset_mix: AssetMixItem[];
  owner_balances: OwnerBalanceItem[];
  credit_utilization: CreditUtilizationItem[];
  stale_accounts: StaleAccountItem[];
  forked_accounts: string[];
}

export interface TopCategoryItem {
  category: string;
  amount: number;
}

export interface MonthOverMonthItem {
  category: string;
  period: string;
  amount: number;
}

export interface IncomeBreakdownItem {
  description: string;
  amount: number;
}

export interface SavingsRateTrendItem {
  month: string;
  savings_rate: number;
}

export interface Overview {
  income: number;
  expenses: number;
  net_flow: number;
  savings_rate: number;
  flagged_count: number;
  avg_weekly_expense: number;
  avg_monthly_expense: number;
  avg_weekly_income: number;
  avg_monthly_income: number;
  top_categories: TopCategoryItem[];
  month_over_month: MonthOverMonthItem[];
  emergency_fund_months: number | null;
  income_breakdown: IncomeBreakdownItem[];
  savings_rate_trend: SavingsRateTrendItem[];
}

export interface OverviewResponse {
  net_worth: NetWorth;
  overview: Overview;
}

// ---------------------------------------------------------------------------
// GET /cash-flow
// ---------------------------------------------------------------------------

export interface CashFlowSeriesItem {
  month: string;
  tx_type: string;
  amount: number;
}

export interface WeeklyTrendItem {
  week: string;
  tx_type: string;
  amount: number;
}

export interface RollingSpendItem {
  date: string;
  amount: number;
}

export interface MonthlyNetByOwnerItem {
  month: string;
  owner: string;
  amount: number;
}

export interface CategoryDistributionItem {
  month: string;
  category: string;
  amount: number;
}

export interface CashFlowResponse {
  income: number;
  expenses: number;
  net_flow: number;
  transfer_count: number;
  flagged_count: number;
  savings_rate: number;
  month_over_month: CashFlowSeriesItem[];
  weekly_trend: WeeklyTrendItem[];
  rolling_30d_spend: RollingSpendItem[];
  monthly_net_by_owner: MonthlyNetByOwnerItem[];
  category_distribution: CategoryDistributionItem[];
}

// ---------------------------------------------------------------------------
// GET /budget
// ---------------------------------------------------------------------------

export interface BudgetItem {
  category: string;
  spent: number;
  limit: number | null;
  pct: number | null;
  is_over_budget: boolean;
  projected_eom: number | null;
  is_current_month: boolean;
}

export interface BudgetResponse {
  month: string | null;
  items: BudgetItem[];
}

// ---------------------------------------------------------------------------
// GET /ledger
// ---------------------------------------------------------------------------

export interface LedgerItem {
  hash: string;
  date: string;
  owner_name: string | null;
  account_name: string;
  description: string;
  amount: number;
  category: string | null;
  is_recurring: boolean;
  is_duplicate: boolean;
}

export interface LedgerResponse {
  transactions: LedgerItem[];
}

// ---------------------------------------------------------------------------
// GET /anomalies
// ---------------------------------------------------------------------------

export interface AnomalyItem {
  date: string;
  owner_name: string | null;
  account_name: string;
  description: string;
  amount: number;
  category: string | null;
  outlier_score: number;
}

export interface AnomaliesResponse {
  anomalies: AnomalyItem[];
}

// ---------------------------------------------------------------------------
// GET /categories
// ---------------------------------------------------------------------------

export interface CategoriesResponse {
  categories: string[];
}
