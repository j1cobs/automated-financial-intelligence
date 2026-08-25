/**
 * Tooltip registry for every headline metric (PLAN.md Phase 15, Fix 13).
 *
 * A single source of truth so a metric's label can never drift from its
 * explanation: `MetricTile` reads both `label` and the popover content from
 * the same entry, keyed by the API field name it annotates (mirrors
 * `web/src/lib/polarity.ts`'s `METRIC_POLARITY` convention).
 *
 * `excludes` does real work -- it is what answers "why doesn't this match my
 * bank?", a question currently answered nowhere in the UI.
 */

export interface MetricInfo {
  label: string;
  definition: string;
  formula: string;
  window: string;
  excludes: string[];
}

export const METRIC_INFO: Readonly<Record<string, MetricInfo>> = Object.freeze({
  net_worth: {
    label: 'Net Worth',
    definition: "What you'd have left if you settled every account today.",
    formula: 'total assets − total liabilities',
    window: 'Current balances',
    excludes: [],
  },
  total_assets: {
    label: 'Total Assets',
    definition: 'Everything you hold: chequing, savings, and investments.',
    formula: 'sum of depository and investment balances',
    window: 'Current balances',
    excludes: [],
  },
  total_liabilities: {
    label: 'Total Liabilities',
    definition: 'What you currently owe across credit accounts.',
    formula: 'sum of credit account balances',
    window: 'Current balances',
    excludes: [],
  },
  savings_rate: {
    label: 'Savings Rate',
    definition: 'The share of income you did not spend.',
    formula: '(income − expenses) ÷ income',
    window: 'Selected period',
    excludes: ['Internal transfers between your own accounts', 'Transactions you flagged as duplicates'],
  },
  avg_monthly_income: {
    label: 'Monthly Income',
    definition: 'What you typically take in each month.',
    formula: 'average of monthly income over complete months',
    window: 'Complete months in the selected period',
    excludes: [
      'Internal transfers between your own accounts',
      'Transactions you flagged as duplicates',
      'Partial months, including the current one',
    ],
  },
  avg_monthly_expense: {
    label: 'Monthly Expenses',
    definition: 'What you typically spend each month.',
    formula: 'average of monthly expenses over complete months',
    window: 'Complete months in the selected period',
    excludes: [
      'Internal transfers between your own accounts',
      'Transactions you flagged as duplicates',
      'Partial months, including the current one',
    ],
  },
  avg_monthly_net: {
    label: 'Net Monthly Flow',
    definition: 'What you typically keep each month.',
    formula: 'average monthly income − average monthly expenses',
    window: 'Complete months in the selected period',
    excludes: [
      'Internal transfers between your own accounts',
      'Transactions you flagged as duplicates',
      'Partial months, including the current one',
    ],
  },
  avg_weekly_income: {
    label: 'Weekly Income',
    definition: 'What you typically take in each week.',
    formula: 'average of weekly income',
    window: 'Selected period',
    excludes: ['Internal transfers', 'Duplicate-flagged transactions'],
  },
  avg_weekly_expense: {
    label: 'Weekly Expenses',
    definition: 'What you typically spend each week.',
    formula: 'average of weekly expenses',
    window: 'Selected period',
    excludes: ['Internal transfers', 'Duplicate-flagged transactions'],
  },
  emergency_fund_months: {
    label: 'Emergency Fund',
    definition: 'How long your liquid savings would cover a typical month.',
    formula: 'chequing and savings ÷ average monthly expenses',
    window: 'All history',
    excludes: ['Investment and credit balances'],
  },
  flagged_count: {
    label: 'Flagged',
    definition: 'Transactions the anomaly model scored as unusual.',
    formula: 'count where is_outlier',
    window: 'Selected period',
    excludes: [],
  },
  transfer_count: {
    label: 'Transfers',
    definition: 'Moves between your own accounts.',
    formula: 'count where type is transfer',
    window: 'Selected period',
    excludes: [],
  },
  recurring_monthly_spend: {
    label: 'Committed Monthly Spend',
    definition: 'What you’ve marked recurring, averaged over complete months.',
    formula: 'average of monthly expenses flagged is_recurring',
    window: 'Complete months, all history',
    excludes: ['Transactions you have not flagged as recurring'],
  },
  projected_month_end_expenses: {
    label: 'Projected Month-End Spend',
    definition: 'Your spend so far this month, extrapolated to month end.',
    formula: 'spent so far × (days in month ÷ days elapsed)',
    window: 'Current month',
    excludes: ['Internal transfers between your own accounts', 'Transactions you flagged as duplicates'],
  },
});

/** Lookup helper -- `undefined` for a key not (yet) in the registry, rather
 *  than a thrown error, so a tile can render unlabelled instead of crashing. */
export function metricInfoFor(key: string | null | undefined): MetricInfo | undefined {
  if (!key) return undefined;
  if (!Object.hasOwn(METRIC_INFO, key)) return undefined;
  return METRIC_INFO[key];
}
