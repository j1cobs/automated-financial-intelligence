/**
 * Pure date-range helpers backing the Cash Flow -> Transactions drill-downs
 * (weekly bar preview, rolling-30-day-spend navigate). No React, no DOM --
 * unit-testable on their own, same convention as `lib/polarity.ts`.
 */

/**
 * Parses a `week` string as produced by `api/viewmodels.py::_enrich`:
 * `df["week"] = df["date"].dt.to_period("W-SUN").astype(str)`. A pandas
 * weekly `Period` stringifies as `"YYYY-MM-DD/YYYY-MM-DD"` (Monday through
 * Sunday, both ends inclusive) -- confirmed by running
 * `pd.Period(<date>, freq="W-SUN")` directly rather than assumed from
 * `Period.__str__`'s general docs, since its exact format can vary by
 * frequency.
 *
 * Returns `null` for anything that doesn't match that shape, so a caller can
 * treat an unparseable week as "no drill-down available" instead of crashing.
 */
export function parseWeekRange(week: string): { from: string; to: string } | null {
  const match = /^(\d{4}-\d{2}-\d{2})\/(\d{4}-\d{2}-\d{2})$/.exec(week);
  if (!match) return null;
  return { from: match[1], to: match[2] };
}

/**
 * `YYYY-MM` keys for every calendar month a `[from, to]` day range touches
 * (inclusive of both ends) -- what `DashboardFilters.months` expects when
 * `period === 'custom'`. Returns `[]` for unparseable input.
 */
export function monthsCoveringRange(from: string, to: string): string[] {
  const start = new Date(`${from}T00:00:00`);
  const end = new Date(`${to}T00:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return [];

  const months: string[] = [];
  const cursor = new Date(start.getFullYear(), start.getMonth(), 1);
  const last = new Date(end.getFullYear(), end.getMonth(), 1);
  while (cursor <= last) {
    months.push(`${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, '0')}`);
    cursor.setMonth(cursor.getMonth() + 1);
  }
  return months;
}

/**
 * First/last calendar day of a `"YYYY-MM"` month key, as produced by
 * `CashFlowSeriesItem.month` (the monthly "Income vs Expenses" chart's
 * `xKey`) -- the monthly analogue of `parseWeekRange` above, backing the
 * same click-to-preview drill-down for the monthly chart. Returns `null` for
 * anything that doesn't match `YYYY-MM`, same "no drill-down available"
 * convention as `parseWeekRange`.
 *
 * The last day is computed via `new Date(year, month + 1, 0)` -- JS Date
 * deliberately allows a day-of-month of `0`, which rolls back to the last day
 * of the *previous* month, i.e. the last day of `month` itself. This is the
 * one line that has to get 31-day/30-day/February right; see the paired unit
 * tests below.
 */
export function parseMonthRange(month: string): { from: string; to: string } | null {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  if (!match) return null;
  const year = Number(match[1]);
  const monthIndex = Number(match[2]) - 1;
  if (monthIndex < 0 || monthIndex > 11) return null;
  const lastDay = new Date(year, monthIndex + 1, 0).getDate();
  return {
    from: `${match[1]}-${match[2]}-01`,
    to: `${match[1]}-${match[2]}-${String(lastDay).padStart(2, '0')}`,
  };
}

/**
 * ISO date (`YYYY-MM-DD`) `days` days before `date`. Used for "N days ending
 * on this date" windows, e.g. the rolling 30-day spend chart's own tooltip
 * copy: a plotted `date` is the last day of the 30-day window it summarizes,
 * so the window's start is `daysBefore(date, 29)`. Returns `null` for an
 * unparseable date.
 */
export function daysBefore(date: string, days: number): string | null {
  const d = new Date(`${date}T00:00:00`);
  if (Number.isNaN(d.getTime())) return null;
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}
