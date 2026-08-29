/**
 * Shared Recharts styling (PLAN.md Phase 15, Fix 11).
 *
 * The React equivalent of `_style_chart()` (`app/dashboard.py:306-324`): one
 * place that decides axis, grid, tooltip, legend, margin and mark geometry, so
 * every chart on the page reads as one system instead of each file inventing
 * its own hexes.
 *
 * Colour never appears literally in this file -- it is read at runtime from the
 * CSS custom properties in `src/index.css`, because Recharts needs a real colour
 * string in several props (`stroke`, `fill`, `contentStyle`) and will not
 * resolve a bare `var(...)` there. The read is cached per theme epoch and the
 * cache is invalidated when `data-theme` flips or the OS preference changes, so
 * a theme swap repaints the charts without any `dark:` branch in a component.
 *
 * Geometry follows the `dataviz` mark specs: bars capped at 24px with a 4px
 * rounded data-end, 2px lines, >=8px markers, 10% area washes, solid hairline
 * grid (never dashed), and a 2px surface gap between touching fills.
 */

import { useSyncExternalStore } from 'react';

/* ---------------------------------------------------------------------------
   Runtime token access
   --------------------------------------------------------------------------- */

let epoch = 0;
let cache: Record<string, string> = {};
const listeners = new Set<() => void>();
let watching = false;

/** Invalidate the resolved-colour cache and notify subscribers. */
export function refreshChartTheme(): void {
  epoch += 1;
  cache = {};
  for (const fn of listeners) fn();
}

/**
 * Watch the two things that can change a token's value: the explicit
 * `data-theme` stamp on `<html>`, and the OS colour-scheme preference. Installed
 * lazily and defensively -- jsdom has no `matchMedia`, and a document may not
 * exist at import time.
 */
function startWatching(): void {
  if (watching || typeof document === 'undefined') return;
  watching = true;
  try {
    new MutationObserver(refreshChartTheme).observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });
  } catch {
    /* observer unavailable -- callers can still call refreshChartTheme() */
  }
  try {
    const media = window.matchMedia?.('(prefers-color-scheme: dark)');
    media?.addEventListener?.('change', refreshChartTheme);
  } catch {
    /* matchMedia unavailable (jsdom) */
  }
}

/**
 * Resolve one CSS custom property off `<html>`. `fallback` covers SSR, jsdom,
 * and the frame before stylesheets apply -- a chart must never render with an
 * empty colour string.
 */
export function cssVar(name: string, fallback: string): string {
  startWatching();
  const hit = cache[name];
  if (hit !== undefined) return hit;
  let value = '';
  if (typeof document !== 'undefined') {
    try {
      value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    } catch {
      value = '';
    }
  }
  const resolved = value || fallback;
  cache[name] = resolved;
  return resolved;
}

function subscribe(fn: () => void): () => void {
  startWatching();
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/**
 * Re-render a chart when the theme changes. Returns the epoch, which is only
 * useful as a `key`/dependency -- the colours themselves come from the
 * accessors below, which are cache-invalidated by the same event.
 */
export function useChartTheme(): number {
  return useSyncExternalStore(
    subscribe,
    () => epoch,
    () => epoch,
  );
}

/* ---------------------------------------------------------------------------
   Palette accessors
   --------------------------------------------------------------------------- */

/** Chart surface -- also the colour of the two `dataviz` spacers. */
export const surfaceColor = () => cssVar('--chart-surface', '#fcfcfb');
export const gridColor = () => cssVar('--chart-grid', '#e1e0d9');
export const axisColor = () => cssVar('--chart-axis', '#c3c2b7');
export const axisLabelColor = () => cssVar('--chart-axis-label', '#52514e');
export const inkColor = () => cssVar('--text-primary', '#0b0b0b');
export const inkSecondaryColor = () => cssVar('--text-secondary', '#52514e');
export const inkMutedColor = () => cssVar('--text-muted', '#898781');
export const hairlineColor = () => cssVar('--border-hairline', 'rgb(11 11 11 / 0.1)');

/** Semantic (state) colours. Never use these for series identity. */
export const positiveColor = () => cssVar('--pos', '#0ca30c');
export const negativeColor = () => cssVar('--neg', '#d03b3b');
export const neutralColor = () => cssVar('--neutral', '#898781');

/**
 * Cash-flow roles. Income and expense are two *series* -- identity, not
 * polarity -- so they wear categorical slots. Painting expense red would say
 * "expenses are bad news" about every expense, including the rent.
 */
export const incomeColor = () => cssVar('--flow-income', '#2a78d6');
export const expenseColor = () => cssVar('--flow-expense', '#eb6834');

const CATEGORICAL_FALLBACK = [
  '#2a78d6',
  '#eb6834',
  '#1baf7a',
  '#eda100',
  '#e87ba4',
  '#008300',
  '#4a3aa7',
  '#e34948',
];

/** How many distinct categorical hues exist. There is deliberately no 9th. */
export const CATEGORICAL_SLOTS = 8;

/**
 * Categorical slot by index, in fixed order and **never cycled** -- the order
 * is the colourblind-safety mechanism, so a 9th hue is not generated. Index 8
 * and beyond return the neutral "Other" colour; the caller is expected to have
 * folded the tail into an "Other" bucket (or faceted) before it gets here.
 *
 * Colour follows the *entity*, so callers must key the index off a stable
 * sorted category list -- never off the current filtered row number, or
 * filtering repaints the survivors.
 *
 * Three light-mode slots (aqua, yellow, magenta) sit below 3:1 on the light
 * surface. That is validated and allowed only with a relief channel: those
 * series need visible direct labels or the table view, not colour alone.
 */
export function categoricalColor(index: number): string {
  if (!Number.isFinite(index) || index < 0 || index >= CATEGORICAL_SLOTS) {
    return neutralColor();
  }
  const slot = Math.floor(index);
  return cssVar(`--cat-${slot + 1}`, CATEGORICAL_FALLBACK[slot]);
}

/** Series-identity colours for `n` categories, `n <= CATEGORICAL_SLOTS`. */
export function categoricalScale(n: number): string[] {
  return Array.from({ length: Math.max(0, n) }, (_, i) => categoricalColor(i));
}

const SEQUENTIAL_FALLBACK = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b'];

/** Number of stops in the sequential ramp. */
export const SEQUENTIAL_STOPS = SEQUENTIAL_FALLBACK.length;

function parseHex(hex: string): [number, number, number] | null {
  const m = /^#?([\da-f]{6})$/i.exec(hex.trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function toHex(rgb: [number, number, number]): string {
  return `#${rgb.map((c) => Math.round(c).toString(16).padStart(2, '0')).join('')}`;
}

/**
 * Magnitude -> colour along the single-hue sequential ramp. `t` is normalised
 * 0..1 where 0 is "near zero" and 1 is the maximum in view.
 *
 * The ramp's anchor flips in dark mode (near-zero recedes toward whichever
 * surface is behind it), so this needs no mode branch: `--seq-1` always means
 * "least" and `--seq-7` always means "most".
 *
 * One hue, light to dark -- never a rainbow. A continuous scale like this must
 * ship a scale legend and a table view; colour is not allowed to be the only
 * way to read a cell.
 */
export function sequentialColor(t: number): string {
  const clamped = Number.isFinite(t) ? Math.min(1, Math.max(0, t)) : 0;
  const pos = clamped * (SEQUENTIAL_STOPS - 1);
  const lo = Math.floor(pos);
  const hi = Math.min(SEQUENTIAL_STOPS - 1, lo + 1);
  const frac = pos - lo;
  const a = cssVar(`--seq-${lo + 1}`, SEQUENTIAL_FALLBACK[lo]);
  const b = cssVar(`--seq-${hi + 1}`, SEQUENTIAL_FALLBACK[hi]);
  if (frac === 0) return a;
  const rgbA = parseHex(a);
  const rgbB = parseHex(b);
  if (!rgbA || !rgbB) return frac < 0.5 ? a : b;
  return toHex([
    rgbA[0] + (rgbB[0] - rgbA[0]) * frac,
    rgbA[1] + (rgbB[1] - rgbA[1]) * frac,
    rgbA[2] + (rgbB[2] - rgbA[2]) * frac,
  ]);
}

/**
 * Text colour for a label placed *inside* a sequential cell -- picked by the
 * fill's luminance so an in-fill label always clears contrast. This is the one
 * case where text is allowed to sit on a data colour.
 */
export function onFillTextColor(fill: string): string {
  const rgb = parseHex(fill);
  if (!rgb) return inkColor();
  const [r, g, b] = rgb.map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return luminance > 0.4
    ? cssVar('--text-on-light-fill', '#0b0b0b')
    : cssVar('--text-on-dark-fill', '#ffffff');
}

/* ---------------------------------------------------------------------------
   Recharts prop objects
   --------------------------------------------------------------------------- */

/**
 * Margins. `compact` is the mobile default: the y-axis carries its own `width`,
 * so the left margin only needs to stop the first tick label being clipped.
 * `wide` is for charts with rotated or long x-axis labels.
 *
 * Whatever the margin, size the *container* to include the x-axis band -- a
 * fixed height that excludes it produces a tiny nested scrollbar inside the card.
 */
export const CHART_MARGIN = Object.freeze({
  compact: Object.freeze({ top: 8, right: 8, bottom: 0, left: 0 }),
  default: Object.freeze({ top: 12, right: 16, bottom: 4, left: 4 }),
  wide: Object.freeze({ top: 12, right: 16, bottom: 28, left: 4 }),
});

export const AXIS_FONT_SIZE = 12;

/** Solid hairline grid, one step off the surface. Horizontal only -- vertical
 *  rules duplicate the category ticks. Never dashed. */
export function gridProps() {
  return {
    stroke: gridColor(),
    strokeWidth: 1,
    vertical: false,
    horizontal: true,
  } as const;
}

/** Category (usually x) axis. `minTickGap` is what keeps a month axis readable
 *  at 360px instead of overlapping into mush. */
export function xAxisProps() {
  return {
    stroke: axisColor(),
    tickLine: false,
    axisLine: { stroke: axisColor() },
    tick: { fill: axisLabelColor(), fontSize: AXIS_FONT_SIZE },
    minTickGap: 16,
    tickMargin: 8,
  } as const;
}

/**
 * Value (usually y) axis. `width` is fixed so charts in a grid align, and
 * tabular figures keep the tick column from shifting.
 *
 * There is exactly one value axis per plot. A second y-scale invents a
 * correlation the data does not contain; two measures of different magnitude
 * mean two charts or one indexed scale.
 */
export function yAxisProps(width = 56) {
  return {
    stroke: axisColor(),
    tickLine: false,
    axisLine: false,
    tick: { fill: axisLabelColor(), fontSize: AXIS_FONT_SIZE },
    width,
    tickMargin: 4,
  } as const;
}

/**
 * Character budget for a category-axis tick label at a 160px axis width
 * (`AXIS_FONT_SIZE` 12, so ~6.6px/char average advance width for a sans-serif
 * face, minus `tickMargin` and internal tick padding). Recharts hard-clips
 * category tick text with no ellipsis when it overflows the axis's `width` --
 * there is no built-in truncation for a category axis the way there is for a
 * numeric one, so `truncateTickLabel` below does it by hand. The full,
 * untruncated value is still available on hover: Recharts derives a vertical
 * bar chart's tooltip label from the category axis's raw data value, not from
 * `tickFormatter`'s output, so truncating the tick never truncates the
 * tooltip.
 */
export const CATEGORY_TICK_CHAR_BUDGET = 22;

/** Truncate a category-axis tick label to `maxChars`, trailing "…" when cut. */
export function truncateTickLabel(value: string, maxChars: number = CATEGORY_TICK_CHAR_BUDGET): string {
  if (value.length <= maxChars) return value;
  return `${value.slice(0, Math.max(0, maxChars - 1))}…`;
}

/** Tooltip chrome. Enhances -- never the only way to read a value. */
export function tooltipProps() {
  return {
    // `fill` is required here: Recharts' Bar-chart hover cursor falls back to
    // its own hardcoded light-gray default when none is given, which reads as
    // a stray light patch on a dark surface. Reuses `AREA_FILL_OPACITY` (the
    // existing "series hue at 10%, never a saturated block" convention) rather
    // than inventing a new translucency value.
    cursor: { stroke: axisColor(), strokeWidth: 1, fill: axisColor(), fillOpacity: AREA_FILL_OPACITY },
    contentStyle: {
      backgroundColor: surfaceColor(),
      border: `1px solid ${hairlineColor()}`,
      borderRadius: 8,
      boxShadow: '0 4px 16px rgb(0 0 0 / 0.12)',
      fontSize: AXIS_FONT_SIZE,
      padding: '8px 10px',
    },
    labelStyle: { color: inkColor(), fontWeight: 600, marginBottom: 4 },
    itemStyle: { color: inkSecondaryColor(), padding: 0 },
  } as const;
}

/**
 * Legend. Present for two or more series -- identity must never rest on colour
 * matching alone. A single-series chart gets no legend: its title names it, and
 * a one-swatch box just restates the title.
 */
export function legendProps() {
  return {
    wrapperStyle: {
      fontSize: AXIS_FONT_SIZE,
      color: inkSecondaryColor(),
      paddingTop: 8,
    },
    iconSize: 10,
    iconType: 'plainline' as const,
  };
}

/* ---------------------------------------------------------------------------
   Mark geometry
   --------------------------------------------------------------------------- */

/** Line: 2px, round joins, no per-point dots (a dot per point is noise). */
export const LINE_PROPS = Object.freeze({
  type: 'monotone' as const,
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  dot: false as const,
});

/** Active/hover marker: >= 8px diameter, with the 2px surface ring that keeps
 *  it legible where it crosses another line. */
export function activeDotProps() {
  return { r: 4, strokeWidth: 2, stroke: surfaceColor() } as const;
}

/** Bar: capped thickness so the band keeps some air, 4px rounded data-end,
 *  square at the baseline. */
export const BAR_MAX_SIZE = 24;
export const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0];
/** Horizontal bars grow right, so the rounded end is on the right. */
export const BAR_RADIUS_HORIZONTAL: [number, number, number, number] = [0, 4, 4, 0];

/**
 * The 2px surface gap between touching fills -- stacked segments and adjacent
 * bars alike. Spread onto a `<Bar>`. This is a spacer in the surface colour,
 * not a border: it is white doing the separating, so no extra ink lands on the
 * chart.
 */
export function surfaceGapProps() {
  return { stroke: surfaceColor(), strokeWidth: 2 } as const;
}

/** Area wash: the series hue at 10%, never a saturated block. */
export const AREA_FILL_OPACITY = 0.1;

/** Zero rule / target reference line. */
export function referenceLineProps() {
  return { stroke: axisColor(), strokeWidth: 1 } as const;
}
