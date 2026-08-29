import { describe, it, expect } from 'vitest';
import { METRIC_INFO, metricInfoFor } from './metricInfo';

/**
 * The full set of metric keys actually rendered by `OverviewTab`,
 * `CashFlowTab`, and `HomeTab` (PLAN.md Phase 15, Fix 13). Kept as an explicit
 * manifest, not derived by scanning the components, so this test
 * independently pins the contract: every key here must resolve, and
 * `METRIC_INFO` must carry no orphan entries beyond it.
 */
const RENDERED_METRIC_KEYS = [
  'income',
  'expenses',
  'net_flow',
  'net_worth',
  'total_assets',
  'total_liabilities',
  'savings_rate',
  'avg_monthly_income',
  'avg_monthly_expense',
  'avg_monthly_net',
  'avg_weekly_income',
  'avg_weekly_expense',
  'emergency_fund_months',
  'flagged_count',
  'transfer_count',
  'recurring_monthly_spend',
  'projected_month_end_expenses',
] as const;

describe('METRIC_INFO', () => {
  it('has an entry for every metric key actually rendered', () => {
    for (const key of RENDERED_METRIC_KEYS) {
      expect(METRIC_INFO[key], `missing metricInfo entry for "${key}"`).toBeDefined();
    }
  });

  it('has no orphan entries beyond the rendered set', () => {
    const registryKeys = Object.keys(METRIC_INFO).sort();
    const renderedKeys = [...RENDERED_METRIC_KEYS].sort();
    expect(registryKeys).toEqual(renderedKeys);
  });

  it('every entry has a non-empty label, definition, formula, and window', () => {
    for (const [key, info] of Object.entries(METRIC_INFO)) {
      expect(info.label, key).not.toBe('');
      expect(info.definition, key).not.toBe('');
      expect(info.formula, key).not.toBe('');
      expect(info.window, key).not.toBe('');
      expect(Array.isArray(info.excludes), key).toBe(true);
    }
  });

  it('matches the specified content for savings_rate exactly', () => {
    expect(METRIC_INFO.savings_rate).toEqual({
      label: 'Savings Rate',
      definition: 'The share of income you did not spend.',
      formula: '(income − expenses) ÷ income',
      window: 'Selected period',
      excludes: ['Internal transfers between your own accounts', 'Transactions you flagged as duplicates'],
    });
  });

  it('matches the specified content for avg_monthly_income exactly', () => {
    expect(METRIC_INFO.avg_monthly_income).toEqual({
      label: 'Monthly Income',
      definition: 'What you typically take in each month.',
      formula: 'average of monthly income over complete months',
      window: 'Complete months in the selected period',
      excludes: [
        'Internal transfers between your own accounts',
        'Transactions you flagged as duplicates',
        'Partial months, including the current one',
      ],
    });
  });

  it('matches the specified content for emergency_fund_months exactly', () => {
    expect(METRIC_INFO.emergency_fund_months).toEqual({
      label: 'Emergency Fund',
      definition: 'How long your liquid savings would cover a typical month.',
      formula: 'chequing and savings ÷ average monthly expenses',
      window: 'All history',
      excludes: ['Investment and credit balances'],
    });
  });
});

describe('metricInfoFor', () => {
  it('returns the entry for a known key', () => {
    expect(metricInfoFor('net_worth')?.label).toBe('Net Worth');
  });

  it('returns undefined rather than throwing for an unknown or missing key', () => {
    expect(metricInfoFor('some_new_api_field')).toBeUndefined();
    expect(metricInfoFor(null)).toBeUndefined();
    expect(metricInfoFor(undefined)).toBeUndefined();
    expect(metricInfoFor('')).toBeUndefined();
  });

  it('does not resolve prototype members via a bare lookup', () => {
    expect(metricInfoFor('toString')).toBeUndefined();
  });
});
