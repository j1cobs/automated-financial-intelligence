import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { parseWeekRange, monthsCoveringRange, daysBefore, parseMonthRange } from './dateRanges';

describe('parseWeekRange', () => {
  it('parses a "YYYY-MM-DD/YYYY-MM-DD" pandas Period(freq="W-SUN") string', () => {
    expect(parseWeekRange('2024-01-08/2024-01-14')).toEqual({ from: '2024-01-08', to: '2024-01-14' });
  });

  it('parses a range that spans a month boundary', () => {
    expect(parseWeekRange('2024-01-29/2024-02-04')).toEqual({ from: '2024-01-29', to: '2024-02-04' });
  });

  it('returns null for an unrecognized format', () => {
    expect(parseWeekRange('2024-W05')).toBeNull();
    expect(parseWeekRange('')).toBeNull();
    expect(parseWeekRange('2024-01-08')).toBeNull();
  });
});

describe('monthsCoveringRange', () => {
  it('returns a single month key when the range sits inside one month', () => {
    expect(monthsCoveringRange('2024-01-08', '2024-01-14')).toEqual(['2024-01']);
  });

  it('returns every month key touched by a range spanning a boundary', () => {
    expect(monthsCoveringRange('2024-01-29', '2024-02-04')).toEqual(['2024-01', '2024-02']);
  });

  it('returns every month key across a range spanning more than two months', () => {
    expect(monthsCoveringRange('2023-11-15', '2024-02-04')).toEqual([
      '2023-11',
      '2023-12',
      '2024-01',
      '2024-02',
    ]);
  });

  it('returns an empty array for unparseable input', () => {
    expect(monthsCoveringRange('not-a-date', '2024-02-04')).toEqual([]);
  });
});

describe('parseMonthRange', () => {
  it('returns the first/last day of a 31-day month', () => {
    expect(parseMonthRange('2026-08')).toEqual({ from: '2026-08-01', to: '2026-08-31' });
  });

  it('returns the first/last day of a 30-day month', () => {
    expect(parseMonthRange('2026-04')).toEqual({ from: '2026-04-01', to: '2026-04-30' });
  });

  it('returns the first/last day of February in a non-leap year', () => {
    expect(parseMonthRange('2026-02')).toEqual({ from: '2026-02-01', to: '2026-02-28' });
  });

  it('returns the first/last day of February in a leap year', () => {
    expect(parseMonthRange('2024-02')).toEqual({ from: '2024-02-01', to: '2024-02-29' });
  });

  it('returns null for an unrecognized format', () => {
    expect(parseMonthRange('2026-08-01')).toBeNull();
    expect(parseMonthRange('2026')).toBeNull();
    expect(parseMonthRange('')).toBeNull();
  });
});

describe('daysBefore', () => {
  it('subtracts the given number of days', () => {
    expect(daysBefore('2024-02-01', 29)).toBe('2024-01-03');
  });

  it('crosses a month boundary correctly', () => {
    expect(daysBefore('2024-01-03', 5)).toBe('2023-12-29');
  });

  it('crosses a year boundary correctly', () => {
    expect(daysBefore('2024-01-05', 10)).toBe('2023-12-26');
  });

  it('returns null for an unparseable date', () => {
    expect(daysBefore('not-a-date', 29)).toBeNull();
  });

  describe('timezone handling', () => {
    let originalTz: string | undefined;

    beforeEach(() => {
      originalTz = process.env.TZ;
    });

    afterEach(() => {
      process.env.TZ = originalTz;
    });

    it('returns correct date in positive UTC-offset timezone (regression test for UTC round-trip bug)', () => {
      // Set timezone to Pacific/Kiritimati (UTC+14), the easternmost timezone.
      // In UTC+14, local midnight is 14 hours behind UTC midnight, so toISOString()
      // would incorrectly shift the date backward if used. This test ensures we
      // construct the date string from local getters instead.
      process.env.TZ = 'Pacific/Kiritimati';

      // Constructing dates forces Node.js to recompute timezone info when
      // the environment variable changes, but a running V8 isolate may cache it.
      // Force cache invalidation by parsing a test date after setting TZ.
      new Date('2024-01-15T00:00:00');

      // daysBefore should return the date 5 days before 2024-01-15, regardless
      // of the system timezone. The fix ensures we use local getters (getFullYear,
      // getMonth, getDate) instead of toISOString().
      expect(daysBefore('2024-01-15', 5)).toBe('2024-01-10');
    });
  });
});
