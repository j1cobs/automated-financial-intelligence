/**
 * Direction-aware metric semantics (PLAN.md Phase 15, Fix 11).
 *
 * The bug this exists to kill: green/red were encoding *income vs expense* in
 * one component and *good vs bad* in another, so a large expense and a healthy
 * surplus could render the same colour. The fix splits the two vocabularies:
 *
 *   identity  (which series is this?)   -> the categorical tokens, `--cat-N`
 *   polarity  (is this good or bad?)    -> the semantic tokens, `--pos`/`--neg`
 *
 * Whether "up" is good is a property of the *metric*, not of the component
 * rendering it, so it is decided exactly once here. Spending more is bad;
 * earning more is good; saving a larger share is good. Everything downstream
 * (a `<DeltaBadge>`, a sparkline accent, a KPI tile) reads `toneFor()` and does
 * not re-decide.
 *
 * Pure functions only -- no React, no DOM, no CSS. Colour is applied at the
 * edge by mapping a tone to `TONE_TOKENS`.
 */

/**
 * `'normal'` -- an increase in this metric is good (income, net worth).
 * `'inverse'` -- an increase in this metric is bad (spend, utilisation, debt).
 * `'neutral'` -- movement carries no valence at all (transaction count), so a
 * delta is never painted good or bad.
 */
export type Polarity = 'normal' | 'inverse' | 'neutral';

/** What a delta *means*, once polarity has been applied. */
export type Tone = 'good' | 'bad' | 'neutral';

/** Which way the number moved, before polarity is applied. */
export type Direction = 'up' | 'down' | 'flat';

/**
 * Metric key -> polarity. Keys mirror the API view-model field names
 * (`api/viewmodels.py`) so a tile can pass the field it already has.
 *
 * Anything absent falls back to `DEFAULT_POLARITY`. Adding a metric to the API
 * therefore never *silently* mis-paints it -- it just renders unvalenced until
 * it is listed here.
 */
export const METRIC_POLARITY: Readonly<Record<string, Polarity>> = Object.freeze({
  // more is better
  net_worth: 'normal',
  assets: 'normal',
  net_flow: 'normal',
  savings_rate: 'normal',
  income: 'normal',
  total_income: 'normal',
  avg_monthly_income: 'normal',
  avg_weekly_income: 'normal',
  available_credit: 'normal',
  balance_current: 'normal',

  // more is worse
  expenses: 'inverse',
  total_expenses: 'inverse',
  avg_monthly_expense: 'inverse',
  avg_weekly_expense: 'inverse',
  rolling_30d_spend: 'inverse',
  total_spend: 'inverse',
  category_spend: 'inverse',
  budget_spend: 'inverse',
  budget_pct: 'inverse',
  credit_utilization: 'inverse',
  liabilities: 'inverse',
  outlier_count: 'inverse',

  // movement is just movement
  transaction_count: 'neutral',
  account_count: 'neutral',
});

/** Used for any metric key not listed in {@link METRIC_POLARITY}. */
export const DEFAULT_POLARITY: Polarity = 'neutral';

/**
 * Polarity for a metric key. Unknown keys return `DEFAULT_POLARITY` rather than
 * guessing -- an unvalenced delta is a smaller error than a confidently wrong
 * colour.
 */
export function polarityOf(metricKey: string | null | undefined): Polarity {
  if (!metricKey) return DEFAULT_POLARITY;
  // `hasOwn`, not a bare lookup: a metric key arrives from API data, and
  // `METRIC_POLARITY['toString']` would otherwise resolve to a prototype member.
  if (!Object.hasOwn(METRIC_POLARITY, metricKey)) return DEFAULT_POLARITY;
  return METRIC_POLARITY[metricKey];
}

/**
 * Which way a delta points. `epsilon` collapses noise around zero to `'flat'`
 * (a rounded 0.0% should not render an arrow). Non-finite input is `'flat'`.
 */
export function directionOf(delta: number | null | undefined, epsilon = 0): Direction {
  if (delta == null || !Number.isFinite(delta)) return 'flat';
  if (Math.abs(delta) <= epsilon) return 'flat';
  return delta > 0 ? 'up' : 'down';
}

/**
 * The whole point of the module: combine a signed delta with the metric's
 * polarity to get a tone.
 *
 *   +$400 on income                (normal)  -> 'good'
 *   +$400 on spend                 (inverse) -> 'bad'
 *   -2pp  on credit utilisation    (inverse) -> 'good'
 *   any delta on transaction count (neutral) -> 'neutral'
 *
 * A zero, missing, or non-finite delta is always `'neutral'`.
 */
export function toneFor(delta: number | null | undefined, polarity: Polarity, epsilon = 0): Tone {
  const direction = directionOf(delta, epsilon);
  if (direction === 'flat' || polarity === 'neutral') return 'neutral';
  const isGood = polarity === 'normal' ? direction === 'up' : direction === 'down';
  return isGood ? 'good' : 'bad';
}

/** Convenience: `toneFor` straight from a metric key. */
export function toneForMetric(
  metricKey: string | null | undefined,
  delta: number | null | undefined,
  epsilon = 0,
): Tone {
  return toneFor(delta, polarityOf(metricKey), epsilon);
}

/**
 * Tone -> CSS custom properties, as `var(...)` strings for style props.
 *
 * `fill` is for marks (bars, dots, rules); `text` is a darker/lighter step that
 * clears WCAG 4.5:1 small-text contrast on its own surface in both modes --
 * `fill` does not, so never set `color` from `fill`.
 */
export const TONE_TOKENS: Readonly<Record<Tone, { fill: string; text: string }>> = Object.freeze({
  good: { fill: 'var(--pos)', text: 'var(--pos-text)' },
  bad: { fill: 'var(--neg)', text: 'var(--neg-text)' },
  neutral: { fill: 'var(--neutral)', text: 'var(--neutral-text)' },
});

/**
 * The glyph a tone must ship with. The semantic palette sits close in hue to
 * two of the categorical slots (eight hues cover the wheel; green and red are
 * among them), so hue is never allowed to carry good/bad on its own -- a tone
 * is always rendered as icon + label + colour. Callers that drop the glyph are
 * violating the accessibility contract, not saving space.
 */
export const DIRECTION_GLYPH: Readonly<Record<Direction, string>> = Object.freeze({
  up: '↑',
  down: '↓',
  flat: '→',
});

/**
 * Screen-reader / tooltip text for a delta. Returned instead of rendered so
 * this file stays JSX-free and unit-testable.
 */
export function toneLabel(direction: Direction, tone: Tone): string {
  if (direction === 'flat') return 'unchanged';
  const word = direction === 'up' ? 'up' : 'down';
  if (tone === 'neutral') return word;
  return `${word} (${tone === 'good' ? 'better' : 'worse'})`;
}
