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

export interface OwnerAccountItem {
  account_name: string;
  type: string;
  value: number;
}

export interface OwnerBalanceItem {
  owner: string;
  depository: number;
  investment: number;
  credit: number;
  other: number;
  net: number;
  accounts: OwnerAccountItem[];
}

export interface CreditUtilizationItem {
  account_key: string;
  account_name: string;
  owner_name: string | null;
  current: number;
  limit: number | null;
  pct: number | null;
  is_manual: boolean;
}

export interface StaleAccountItem {
  account_key: string;
  account_name: string;
  days_stale: number;
}

export interface DormantAccountItem {
  account_key: string;
  account_name: string;
  owner_name: string | null;
  days_inactive: number;
  balance: number;
}

export interface NetWorth {
  net_worth: number;
  total_assets: number;
  total_liabilities: number;
  asset_mix: AssetMixItem[];
  owner_balances: OwnerBalanceItem[];
  credit_utilization: CreditUtilizationItem[];
  stale_accounts: StaleAccountItem[];
  dormant_accounts: DormantAccountItem[];
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
  savings_rate: number | null;
  income: number;
  expenses: number;
}

export interface MetricSummary {
  key: string;
  value: number;
  /** The same quantity averaged over every complete month of history. `null`
   * when there is not a single complete month to average. */
  baseline: number | null;
  /** Fraction: `(value - baseline) / abs(baseline)`. `null` when `baseline`
   * is absent or zero. */
  delta_pct: number | null;
  baseline_months: number;
  /** Up to the last 12 complete months of the underlying monthly series. */
  sparkline: number[];
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
  avg_monthly_net: number;
  complete_months: number;
  /** Baseline/sparkline context, keyed by the field name it annotates. */
  metrics: Record<string, MetricSummary>;
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
  income: number;
  expenses: number;
  net: number;
}

export interface WeeklyTrendItem {
  week: string;
  income: number;
  expenses: number;
  net: number;
}

export interface RollingSpendItem {
  date: string;
  amount: number;
  daily_avg: number;
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
// GET /home
// ---------------------------------------------------------------------------

export interface NetWorthTrendItem {
  date: string;
  net_worth: number;
}

export interface RecurringItem {
  description: string;
  amount: number;
}

export interface MerchantItem {
  description: string;
  amount: number;
}

export interface CashFlowProjection {
  month: string;
  spent_so_far: number;
  income_so_far: number;
  projected_expenses: number;
  projected_income: number;
  days_elapsed: number;
  days_in_month: number;
}

export interface CategoryDriftItem {
  category: string;
  current: number;
  /** The category's own historical average over complete months, not a budget. */
  baseline: number;
  /** Fraction: `(current - baseline) / baseline`. Positive = spending more than usual. */
  drift_pct: number;
}

export interface SubscriptionItem {
  description: string;
  average_amount: number;
  /** Out of the trailing 6 months. */
  months_seen: number;
}

export interface BiggestExpenseItem {
  description: string;
  amount: number;
  date: string;
}

export interface UpcomingRecurringItem {
  description: string;
  amount: number;
  /** A median-interval projection, not a confirmed billing date. */
  next_expected_date: string;
  typical_interval_days: number;
}

export interface HomeResponse {
  net_worth_trend: NetWorthTrendItem[];
  /** Latest net worth minus the closest sample at least one calendar month prior.
   *  `null` when there isn't a full month of history yet. */
  net_worth_mom_delta: number | null;
  recurring_monthly_spend: number;
  recurring_items: RecurringItem[];
  top_merchants: MerchantItem[];
  cash_flow_projection: CashFlowProjection | null;
  category_drift: CategoryDriftItem[];
  subscriptions: SubscriptionItem[];
  biggest_expense_this_month: BiggestExpenseItem | null;
  upcoming_recurring: UpcomingRecurringItem[];
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

// ---------------------------------------------------------------------------
// GET /filter-options
// ---------------------------------------------------------------------------

export interface MonthOption {
  key: string;
  /** Human-readable, e.g. "July 2026". */
  label: string;
}

export interface FilterOptions {
  owners: string[];
  categories: string[];
  accounts: string[];
  months: MonthOption[];
  amount_min: number;
  amount_max: number;
}
