/**
 * TypeScript mirror of `api/filters.py::DashboardFilters` plus the
 * URL <-> filter-state conversions the client needs. Field names and
 * defaults must match the Pydantic model exactly — see that module's
 * docstring for the invariants these filters carry (two-frame filtering,
 * month-granularity periods, etc).
 */

import type { FilterOptions } from './types';

export type PeriodPreset =
  'last_30_days' | 'current_month' | 'last_3_months' | 'last_6_months' | 'ytd' | 'all_time' | 'custom';

const VALID_PERIODS: ReadonlySet<string> = new Set<PeriodPreset>([
  'last_30_days',
  'current_month',
  'last_3_months',
  'last_6_months',
  'ytd',
  'all_time',
  'custom',
]);

// Mirrors api/filters.py::DEFAULT_PERIOD. Deliberately wider than Streamlit's
// last_30_days — see that module's comment.
export const DEFAULT_PERIOD: PeriodPreset = 'last_3_months';

export const PERIOD_LABELS: Record<PeriodPreset, string> = {
  last_30_days: 'Last 30 days',
  current_month: 'This month',
  last_3_months: 'Last 3 months',
  last_6_months: 'Last 6 months',
  ytd: 'Year to date',
  all_time: 'All time',
  custom: 'Custom',
};

export interface DashboardFilters {
  period: PeriodPreset;
  /** Explicit `YYYY-MM` keys; only consulted when period === 'custom'. */
  months: string[] | null;
  owners: string[] | null;
  categories: string[] | null;
  accounts: string[] | null;
  amount_min: number | null;
  amount_max: number | null;
  search: string | null;
  outliers_only: boolean;
  duplicates_only: boolean;
}

export const DEFAULT_FILTERS: DashboardFilters = {
  period: DEFAULT_PERIOD,
  months: null,
  owners: null,
  categories: null,
  accounts: null,
  amount_min: null,
  amount_max: null,
  search: null,
  outliers_only: false,
  duplicates_only: false,
};

// ---------------------------------------------------------------------------
// Filters <-> URLSearchParams
// ---------------------------------------------------------------------------

function appendArray(params: URLSearchParams, key: string, values: string[] | null | undefined): void {
  if (!values || values.length === 0) return;
  for (const value of values) params.append(key, value);
}

/**
 * Build the query string FastAPI expects: repeated keys for array params
 * (`?owners=A&owners=B`), and anything already at its default omitted
 * entirely so a fully-default filter set produces an empty/clean URL.
 */
export function toSearchParams(filters: DashboardFilters): URLSearchParams {
  const params = new URLSearchParams();

  if (filters.period !== DEFAULT_PERIOD) {
    params.set('period', filters.period);
  }
  appendArray(params, 'months', filters.months);
  appendArray(params, 'owners', filters.owners);
  appendArray(params, 'categories', filters.categories);
  appendArray(params, 'accounts', filters.accounts);

  if (filters.amount_min !== null && filters.amount_min !== undefined) {
    params.set('amount_min', String(filters.amount_min));
  }
  if (filters.amount_max !== null && filters.amount_max !== undefined) {
    params.set('amount_max', String(filters.amount_max));
  }
  if (filters.search) {
    params.set('search', filters.search);
  }
  if (filters.outliers_only) {
    params.set('outliers_only', 'true');
  }
  if (filters.duplicates_only) {
    params.set('duplicates_only', 'true');
  }

  return params;
}

function parsePeriod(raw: string | null): PeriodPreset {
  return raw && VALID_PERIODS.has(raw) ? (raw as PeriodPreset) : DEFAULT_PERIOD;
}

function parseArray(params: URLSearchParams, key: string): string[] | null {
  const values = params.getAll(key);
  return values.length > 0 ? values : null;
}

function parseNumber(raw: string | null): number | null {
  if (raw === null || raw === '') return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

function parseBool(raw: string | null): boolean {
  return raw === 'true' || raw === '1';
}

/**
 * Parse a (possibly hand-edited) URL's query string back into filter state.
 * Never throws: an unknown period falls back to the default, a non-numeric
 * amount becomes `null`, and any param can simply be absent.
 */
export function fromSearchParams(params: URLSearchParams): DashboardFilters {
  return {
    period: parsePeriod(params.get('period')),
    months: parseArray(params, 'months'),
    owners: parseArray(params, 'owners'),
    categories: parseArray(params, 'categories'),
    accounts: parseArray(params, 'accounts'),
    amount_min: parseNumber(params.get('amount_min')),
    amount_max: parseNumber(params.get('amount_max')),
    search: params.get('search') || null,
    outliers_only: parseBool(params.get('outliers_only')),
    duplicates_only: parseBool(params.get('duplicates_only')),
  };
}

// ---------------------------------------------------------------------------
// Chips / active-filter summary, for the filter bar UI
// ---------------------------------------------------------------------------

export interface FilterChip {
  /** Stable key for React lists; also identifies which value a chip removes. */
  id: string;
  label: string;
  /** Pure: returns the next filter state with this one thing removed. */
  remove: (filters: DashboardFilters) => DashboardFilters;
}

function monthLabel(key: string, options?: FilterOptions): string {
  return options?.months.find((month) => month.key === key)?.label ?? key;
}

function withoutArrayValue(values: string[] | null, value: string): string[] | null {
  if (!values) return null;
  const next = values.filter((entry) => entry !== value);
  return next.length > 0 ? next : null;
}

/**
 * One chip per active filter *value* (so selecting 3 owners produces 3
 * removable chips), plus one chip for the period when it isn't the default.
 * `options` is optional so chips can render before `/filter-options` has
 * loaded — months just fall back to their raw `YYYY-MM` key.
 */
export function activeFilterChips(filters: DashboardFilters, options?: FilterOptions): FilterChip[] {
  const chips: FilterChip[] = [];

  if (filters.period !== DEFAULT_PERIOD) {
    chips.push({
      id: 'period',
      label: `Period: ${PERIOD_LABELS[filters.period]}`,
      remove: (f) => ({ ...f, period: DEFAULT_PERIOD, months: null }),
    });
  }

  if (filters.period === 'custom' && filters.months) {
    for (const month of filters.months) {
      chips.push({
        id: `months:${month}`,
        label: monthLabel(month, options),
        remove: (f) => ({ ...f, months: withoutArrayValue(f.months, month) }),
      });
    }
  }

  for (const owner of filters.owners ?? []) {
    chips.push({
      id: `owners:${owner}`,
      label: owner,
      remove: (f) => ({ ...f, owners: withoutArrayValue(f.owners, owner) }),
    });
  }

  for (const category of filters.categories ?? []) {
    chips.push({
      id: `categories:${category}`,
      label: category,
      remove: (f) => ({ ...f, categories: withoutArrayValue(f.categories, category) }),
    });
  }

  for (const account of filters.accounts ?? []) {
    chips.push({
      id: `accounts:${account}`,
      label: account,
      remove: (f) => ({ ...f, accounts: withoutArrayValue(f.accounts, account) }),
    });
  }

  if (filters.amount_min !== null || filters.amount_max !== null) {
    const parts: string[] = [];
    if (filters.amount_min !== null) parts.push(`≥ $${filters.amount_min}`);
    if (filters.amount_max !== null) parts.push(`≤ $${filters.amount_max}`);
    chips.push({
      id: 'amount',
      label: `Amount ${parts.join(', ')}`,
      remove: (f) => ({ ...f, amount_min: null, amount_max: null }),
    });
  }

  if (filters.search) {
    chips.push({
      id: 'search',
      label: `Search: "${filters.search}"`,
      remove: (f) => ({ ...f, search: null }),
    });
  }

  if (filters.outliers_only) {
    chips.push({
      id: 'outliers_only',
      label: 'Flagged only',
      remove: (f) => ({ ...f, outliers_only: false }),
    });
  }

  if (filters.duplicates_only) {
    chips.push({
      id: 'duplicates_only',
      label: 'Possible duplicates only',
      remove: (f) => ({ ...f, duplicates_only: false }),
    });
  }

  return chips;
}

/**
 * Number of active filter *axes* (not values) — what a collapsed
 * "Filters (N)" button should show. Custom months count as one axis
 * alongside (not on top of) the period axis, since they're one control.
 */
export function countActiveFilters(filters: DashboardFilters): number {
  let count = 0;
  if (filters.period !== DEFAULT_PERIOD) count += 1;
  if (filters.period === 'custom' && filters.months && filters.months.length > 0) count += 1;
  if (filters.owners && filters.owners.length > 0) count += 1;
  if (filters.categories && filters.categories.length > 0) count += 1;
  if (filters.accounts && filters.accounts.length > 0) count += 1;
  if (filters.amount_min !== null || filters.amount_max !== null) count += 1;
  if (filters.search) count += 1;
  if (filters.outliers_only) count += 1;
  if (filters.duplicates_only) count += 1;
  return count;
}
