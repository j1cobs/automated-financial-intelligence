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
  short_name: string;
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
  this_month: number;
  last_month: number;
  /** The category's average monthly expense across complete months. `null` when
   * there's no baseline history yet for this category. */
  usual: number | null;
  /** Fraction: `(this_month - usual) / usual`, baseline excludes the current
   * in-progress month. `null` when `usual` isn't computable. */
  this_month_drift_pct: number | null;
  /** Fraction: `(last_month - usual) / usual`, using a baseline that ALSO excludes
   * last month itself from the average -- a different, slightly more accurate
   * baseline than `usual` above, computed only for this percentage. `null` when not
   * computable. */
  last_month_drift_pct: number | null;
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

export interface NetWorthTrendDailyItem {
  /** ISO date, one snapshot per calendar day the pipeline actually ran -- can be
   * sparse if the pipeline hasn't run daily. */
  date: string;
  net_worth: number;
  assets: number;
  liabilities: number;
  /** Depository-only balance -- the subset of `assets` that excludes investments. */
  liquid_cash: number;
}

export interface NetWorthTrendMonthlyItem {
  /** `YYYY-MM`. One row per calendar month, resampled from the last daily snapshot
   * observed in that month. */
  month: string;
  net_worth: number;
  savings_rate: number | null;
  /** Fraction: aggregate credit balance that month ÷ today's total credit limit.
   * `null` when no account has a set limit. */
  credit_utilization_pct: number | null;
  /** Liquid cash that month ÷ a trailing 6-month average expense as of that month.
   * `null` until at least one month of expense history exists. */
  emergency_fund_months: number | null;
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
  /** Current value (liquid savings ÷ average monthly expenses), for the Emergency
   * Fund card's meter. `net_worth_trend_monthly[*].emergency_fund_months` is the
   * historical trend version of the same idea, using a different (rolling 6-month)
   * baseline -- the two can legitimately show slightly different current-month
   * numbers; that's expected, not a bug. */
  emergency_fund_months: number | null;
  income_breakdown: IncomeBreakdownItem[];
  savings_rate_trend: SavingsRateTrendItem[];
  // --- Former Home tab content (Phase 23) -----------------------------------------
  net_worth_trend_daily: NetWorthTrendDailyItem[];
  net_worth_trend_monthly: NetWorthTrendMonthlyItem[];
  /** Latest net worth minus the closest snapshot at least one calendar month prior.
   *  `null` when there isn't a full month of history yet. */
  net_worth_mom_delta: number | null;
  recurring_items: RecurringItem[];
  top_merchants: MerchantItem[];
  cash_flow_projection: CashFlowProjection | null;
  biggest_expense_this_month: BiggestExpenseItem | null;
  upcoming_recurring: UpcomingRecurringItem[];
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
// PATCH /transactions/{hash}/category
// ---------------------------------------------------------------------------

export interface CategoryUpdateResponse {
  backfilled_count: number;
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
