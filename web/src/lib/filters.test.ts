import { describe, it, expect } from 'vitest';
import {
  DEFAULT_FILTERS,
  toSearchParams,
  fromSearchParams,
  activeFilterChips,
  countActiveFilters,
  formatDateRangeLabel,
  type DashboardFilters,
} from './filters';
import type { FilterOptions } from './types';

const options: FilterOptions = {
  owners: ['Alice', 'Bob'],
  categories: ['Groceries', 'Utilities'],
  accounts: ['Chase Checking', 'Ally Savings'],
  months: [
    { key: '2026-01', label: 'January 2026' },
    { key: '2026-02', label: 'February 2026' },
  ],
  amount_min: 0,
  amount_max: 5000,
};

describe('toSearchParams', () => {
  it('produces an empty query string for the all-default filter set', () => {
    expect(toSearchParams(DEFAULT_FILTERS).toString()).toBe('');
  });

  it('omits every field still at its default, including a default period', () => {
    const params = toSearchParams({ ...DEFAULT_FILTERS, search: 'coffee' });
    expect(params.get('period')).toBeNull();
    expect(params.get('search')).toBe('coffee');
  });

  it('repeats the key for array params rather than joining them', () => {
    const params = toSearchParams({ ...DEFAULT_FILTERS, owners: ['Alice', 'Bob'] });
    expect(params.getAll('owners')).toEqual(['Alice', 'Bob']);
  });

  it('serializes booleans only when true', () => {
    const params = toSearchParams({ ...DEFAULT_FILTERS, outliers_only: true, duplicates_only: false });
    expect(params.get('outliers_only')).toBe('true');
    expect(params.has('duplicates_only')).toBe(false);
  });

  it('serializes a non-default period', () => {
    const params = toSearchParams({ ...DEFAULT_FILTERS, period: 'last_30_days' });
    expect(params.get('period')).toBe('last_30_days');
  });

  it('serializes date_from/date_to as ISO date strings', () => {
    const params = toSearchParams({ ...DEFAULT_FILTERS, date_from: '2026-05-04', date_to: '2026-05-11' });
    expect(params.get('date_from')).toBe('2026-05-04');
    expect(params.get('date_to')).toBe('2026-05-11');
  });

  it('omits date_from/date_to when null', () => {
    const params = toSearchParams(DEFAULT_FILTERS);
    expect(params.has('date_from')).toBe(false);
    expect(params.has('date_to')).toBe(false);
  });
});

describe('fromSearchParams', () => {
  it('returns exactly DEFAULT_FILTERS for an empty query string', () => {
    expect(fromSearchParams(new URLSearchParams(''))).toEqual(DEFAULT_FILTERS);
  });

  it('falls back to the default period for an unknown/junk value', () => {
    const parsed = fromSearchParams(new URLSearchParams('period=next_century'));
    expect(parsed.period).toBe(DEFAULT_FILTERS.period);
  });

  it('never throws on a hand-edited URL full of garbage', () => {
    const params = new URLSearchParams(
      'period=banana&amount_min=not-a-number&amount_max=&owners=&outliers_only=nope',
    );
    expect(() => fromSearchParams(params)).not.toThrow();
    const parsed = fromSearchParams(params);
    expect(parsed.amount_min).toBeNull();
    expect(parsed.amount_max).toBeNull();
    expect(parsed.outliers_only).toBe(false);
  });

  it('parses a valid numeric amount', () => {
    const parsed = fromSearchParams(new URLSearchParams('amount_min=10.5&amount_max=200'));
    expect(parsed.amount_min).toBe(10.5);
    expect(parsed.amount_max).toBe(200);
  });

  it('parses repeated keys back into an array', () => {
    const parsed = fromSearchParams(new URLSearchParams('categories=Groceries&categories=Utilities'));
    expect(parsed.categories).toEqual(['Groceries', 'Utilities']);
  });

  it('parses date_from/date_to back into ISO date strings', () => {
    const parsed = fromSearchParams(new URLSearchParams('date_from=2026-05-04&date_to=2026-05-11'));
    expect(parsed.date_from).toBe('2026-05-04');
    expect(parsed.date_to).toBe('2026-05-11');
  });

  it('defaults date_from/date_to to null when absent', () => {
    const parsed = fromSearchParams(new URLSearchParams(''));
    expect(parsed.date_from).toBeNull();
    expect(parsed.date_to).toBeNull();
  });
});

describe('round trip', () => {
  const cases: DashboardFilters[] = [
    DEFAULT_FILTERS,
    { ...DEFAULT_FILTERS, period: 'last_30_days' },
    { ...DEFAULT_FILTERS, period: 'custom', months: ['2026-01', '2026-02'] },
    { ...DEFAULT_FILTERS, owners: ['Alice', 'Bob'], categories: ['Groceries'] },
    { ...DEFAULT_FILTERS, accounts: ['Chase Checking'], amount_min: 10, amount_max: 500.5 },
    { ...DEFAULT_FILTERS, search: 'coffee shop', outliers_only: true, duplicates_only: true },
    { ...DEFAULT_FILTERS, date_from: '2026-05-04', date_to: '2026-05-11' },
  ];

  it.each(cases)('fromSearchParams(toSearchParams(f)) deep-equals f (%#)', (filters) => {
    expect(fromSearchParams(toSearchParams(filters))).toEqual(filters);
  });
});

describe('activeFilterChips', () => {
  it('is empty for the default filter set', () => {
    expect(activeFilterChips(DEFAULT_FILTERS)).toEqual([]);
  });

  it('renders one chip per selected owner, category, and account', () => {
    const chips = activeFilterChips(
      { ...DEFAULT_FILTERS, owners: ['Alice', 'Bob'], categories: ['Groceries'] },
      options,
    );
    const labels = chips.map((chip) => chip.label);
    expect(labels).toEqual(expect.arrayContaining(['Alice', 'Bob', 'Groceries']));
  });

  it('uses the human-readable month label when options are available', () => {
    const chips = activeFilterChips({ ...DEFAULT_FILTERS, period: 'custom', months: ['2026-01'] }, options);
    const monthChip = chips.find((chip) => chip.id === 'months:2026-01');
    expect(monthChip?.label).toBe('January 2026');
  });

  it("falls back to the raw month key when options haven't loaded", () => {
    const chips = activeFilterChips({ ...DEFAULT_FILTERS, period: 'custom', months: ['2026-01'] });
    const monthChip = chips.find((chip) => chip.id === 'months:2026-01');
    expect(monthChip?.label).toBe('2026-01');
  });

  it('a chip removal function clears only that value, leaving siblings intact', () => {
    const filters: DashboardFilters = { ...DEFAULT_FILTERS, owners: ['Alice', 'Bob'] };
    const chips = activeFilterChips(filters, options);
    const aliceChip = chips.find((chip) => chip.id === 'owners:Alice')!;
    const next = aliceChip.remove(filters);
    expect(next.owners).toEqual(['Bob']);
  });

  it('removing the last value of an array filter resets it to null (default)', () => {
    const filters: DashboardFilters = { ...DEFAULT_FILTERS, owners: ['Alice'] };
    const chips = activeFilterChips(filters, options);
    const aliceChip = chips.find((chip) => chip.id === 'owners:Alice')!;
    expect(aliceChip.remove(filters)).toEqual(DEFAULT_FILTERS);
  });

  it('removing the period chip also clears months', () => {
    const filters: DashboardFilters = { ...DEFAULT_FILTERS, period: 'custom', months: ['2026-01'] };
    const chips = activeFilterChips(filters, options);
    const periodChip = chips.find((chip) => chip.id === 'period')!;
    expect(periodChip.remove(filters)).toEqual(DEFAULT_FILTERS);
  });

  it('collapses amount_min/amount_max into a single removable chip', () => {
    const filters: DashboardFilters = { ...DEFAULT_FILTERS, amount_min: 10, amount_max: 500 };
    const chips = activeFilterChips(filters, options);
    const amountChips = chips.filter((chip) => chip.id === 'amount');
    expect(amountChips).toHaveLength(1);
    expect(amountChips[0].remove(filters)).toEqual(DEFAULT_FILTERS);
  });

  it('renders exactly one day-range chip when date_from/date_to are set, instead of period/months chips', () => {
    // The shape a drill-down (e.g. rolling-30-day-spend click-through)
    // actually produces: period/months are set as a required "covering"
    // carrier alongside the day-precise bounds -- see
    // `DashboardFilters.date_from`'s docstring.
    const filters: DashboardFilters = {
      ...DEFAULT_FILTERS,
      period: 'custom',
      months: ['2026-07', '2026-08'],
      date_from: '2026-07-27',
      date_to: '2026-08-25',
    };
    const chips = activeFilterChips(filters, options);

    const dayRangeChips = chips.filter((chip) => chip.id === 'date_range');
    expect(dayRangeChips).toHaveLength(1);
    expect(dayRangeChips[0].label).toBe('Jul 27 – Aug 25, 2026');
    expect(chips.some((chip) => chip.id === 'period')).toBe(false);
    expect(chips.some((chip) => chip.id.startsWith('months:'))).toBe(false);
  });

  it('removing the day-range chip clears period, months, date_from, and date_to together', () => {
    const filters: DashboardFilters = {
      ...DEFAULT_FILTERS,
      period: 'custom',
      months: ['2026-07', '2026-08'],
      date_from: '2026-07-27',
      date_to: '2026-08-25',
    };
    const chips = activeFilterChips(filters, options);
    const dayRangeChip = chips.find((chip) => chip.id === 'date_range')!;
    expect(dayRangeChip.remove(filters)).toEqual(DEFAULT_FILTERS);
  });
});

describe('formatDateRangeLabel', () => {
  it('formats a range as "Mon D – Mon D, YYYY"', () => {
    expect(formatDateRangeLabel('2026-07-27', '2026-08-25')).toBe('Jul 27 – Aug 25, 2026');
  });
});

describe('countActiveFilters', () => {
  it('is 0 for the default filter set', () => {
    expect(countActiveFilters(DEFAULT_FILTERS)).toBe(0);
  });

  it('counts one axis per active filter category, not per selected value', () => {
    const filters: DashboardFilters = {
      ...DEFAULT_FILTERS,
      owners: ['Alice', 'Bob', 'Carol'],
      categories: ['Groceries'],
    };
    expect(countActiveFilters(filters)).toBe(2);
  });

  it('counts the amount range as a single axis regardless of which bound is set', () => {
    expect(countActiveFilters({ ...DEFAULT_FILTERS, amount_min: 10 })).toBe(1);
    expect(countActiveFilters({ ...DEFAULT_FILTERS, amount_min: 10, amount_max: 20 })).toBe(1);
  });

  it('counts a day-range (date_from/date_to) as a single axis, not doubled with period/months', () => {
    const filters: DashboardFilters = {
      ...DEFAULT_FILTERS,
      period: 'custom',
      months: ['2026-07', '2026-08'],
      date_from: '2026-07-27',
      date_to: '2026-08-25',
    };
    expect(countActiveFilters(filters)).toBe(1);
  });

  it('does not undercount to 0 when only date_from/date_to are set (period/months absent)', () => {
    const filters: DashboardFilters = { ...DEFAULT_FILTERS, date_from: '2026-07-27', date_to: '2026-08-25' };
    expect(countActiveFilters(filters)).toBe(1);
  });

  it('counts every axis when everything is active (period and custom months count separately)', () => {
    const filters: DashboardFilters = {
      period: 'custom',
      months: ['2026-01'],
      owners: ['Alice'],
      categories: ['Groceries'],
      accounts: ['Chase Checking'],
      amount_min: 10,
      amount_max: 500,
      search: 'coffee',
      outliers_only: true,
      duplicates_only: true,
      date_from: null,
      date_to: null,
    };
    expect(countActiveFilters(filters)).toBe(9);
  });
});
