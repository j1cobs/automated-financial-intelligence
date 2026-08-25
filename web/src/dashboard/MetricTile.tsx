/**
 * A headline figure plus the context needed to read it (PLAN.md Phase 15,
 * Fixes 12 & 13). Composes:
 *   - label + value, both sourced (label) or annotated (tooltip) from the
 *     `metricInfo` registry so a label can never drift from its explanation
 *   - a keyboard-focusable, tap-friendly info popover (a real `<button>`,
 *     never a CSS `:hover`/`title` -- mobile is an explicitly supported
 *     target)
 *   - a delta badge, built strictly from `lib/polarity.ts`'s `toneFor` /
 *     `polarityOf` / `DIRECTION_GLYPH` / `toneLabel` so colour never ships
 *     without a glyph and a text label
 *   - an inline sparkline, rendered only when there are at least 2 points
 *
 * `metric` (a `MetricSummary`) is optional: several tiles rendered from this
 * component (net worth, weekly income/expense, flagged count, ...) have a
 * `metricInfo` entry but no baseline/sparkline from the API yet. Those render
 * label + value + tooltip with no delta/sparkline, which is correct -- a
 * missing comparison is not the same defect as a fake one.
 */

import { useEffect, useId, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { LineChart, Line, ResponsiveContainer } from 'recharts';
import type { MetricSummary } from '../lib/types';
import { metricInfoFor, type MetricInfo } from '../lib/metricInfo';
import { toneFor, polarityOf, directionOf, DIRECTION_GLYPH, toneLabel, TONE_TOKENS } from '../lib/polarity';
import { positiveColor, negativeColor, neutralColor } from './chartTheme';
import { strings } from '../lib/strings';

export type MetricFormat = 'currency' | 'percent' | 'number';

function formatValue(value: number, format: MetricFormat): string {
  if (format === 'currency') {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  }
  if (format === 'percent') {
    return `${(value * 100).toFixed(1)}%`;
  }
  return value.toLocaleString();
}

/** The info-popover trigger + panel, standalone so non-tile contexts (e.g.
 *  the Overview tab's Emergency Fund card) can reuse just the tooltip. */
export function MetricInfoBadge({ metricKey }: { metricKey: string }) {
  const info = metricInfoFor(metricKey);
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popoverId = useId();

  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open]);

  if (!info) return null;

  return (
    <span className="relative inline-block">
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={open}
        aria-controls={popoverId}
        aria-label={strings.metricTile.infoButtonLabel(info.label)}
        onClick={() => setOpen((prev) => !prev)}
        className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-hairline text-[10px] font-semibold text-ink-muted hover:text-ink hover:border-strong"
      >
        ?
      </button>
      {open && <MetricInfoPopover id={popoverId} info={info} />}
    </span>
  );
}

function MetricInfoPopover({ id, info }: { id: string; info: MetricInfo }) {
  return (
    <div
      id={id}
      role="tooltip"
      className="absolute right-0 z-10 mt-1 w-64 rounded-md border border-hairline bg-surface-1 p-3 text-xs shadow-lg"
    >
      <p className="font-semibold text-ink">{info.label}</p>
      <p className="mt-1 text-ink-secondary">{info.definition}</p>
      <p className="mt-2 text-ink-muted">
        <span className="font-medium text-ink-secondary">{strings.metricTile.formulaLabel}: </span>
        {info.formula}
      </p>
      <p className="mt-1 text-ink-muted">
        <span className="font-medium text-ink-secondary">{strings.metricTile.windowLabel}: </span>
        {info.window}
      </p>
      {info.excludes.length > 0 && (
        <div className="mt-2">
          <p className="font-medium text-ink-secondary">{strings.metricTile.excludesLabel}:</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-ink-muted">
            {info.excludes.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** Glyph + colour + text label -- never colour alone. See `lib/polarity.ts`. */
function DeltaBadge({ metricKey, metric }: { metricKey: string; metric: MetricSummary }) {
  const polarity = polarityOf(metricKey);
  const direction = directionOf(metric.delta_pct);
  const tone = toneFor(metric.delta_pct, polarity);
  return (
    <span
      className="inline-flex items-center gap-1 text-xs font-medium"
      style={{ color: TONE_TOKENS[tone].text }}
    >
      <span aria-hidden="true">{DIRECTION_GLYPH[direction]}</span>
      <span>{toneLabel(direction, tone)}</span>
    </span>
  );
}

function toneStrokeColor(tone: 'good' | 'bad' | 'neutral'): string {
  if (tone === 'good') return positiveColor();
  if (tone === 'bad') return negativeColor();
  return neutralColor();
}

/** No axes, no grid, no tooltip -- the cheapest possible "is this normal?"
 *  shape indicator. Renders nothing under 2 points. */
function Sparkline({ metricKey, metric }: { metricKey: string; metric: MetricSummary }) {
  if (metric.sparkline.length < 2) return null;
  const tone = toneFor(metric.delta_pct, polarityOf(metricKey));
  const data = metric.sparkline.map((v, i) => ({ i, v }));
  return (
    <div className="h-8 w-20 shrink-0" data-testid="metric-sparkline">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <Line
            type="monotone"
            dataKey="v"
            stroke={toneStrokeColor(tone)}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export interface MetricTileProps {
  /** Key into `metricInfo.ts` -- also what `lib/polarity.ts` reads for
   *  polarity. Doubles as the tile's label source. */
  metricKey: string;
  value: number;
  format?: MetricFormat;
  /** Baseline/delta/sparkline context. Absent renders value + tooltip only. */
  metric?: MetricSummary;
  /** Extra caption under the value, e.g. "avg of 3 complete months". */
  sublabel?: string;
  /**
   * When provided, the whole tile becomes a clickable/focusable drill-down
   * target (PLAN.md Phase 15, Fix 13) -- e.g. HomeTab wires this to switch
   * the dashboard to the tab that has the fuller picture for this metric.
   * Rendered as `role="button"` on the tile's own container rather than a
   * real `<button>`, because the tile already nests the info-popover
   * `<button>` and interactive controls cannot nest in valid HTML.
   */
  onDrillDown?: () => void;
}

export function MetricTile({
  metricKey,
  value,
  format = 'currency',
  metric,
  sublabel,
  onDrillDown,
}: MetricTileProps) {
  const info = metricInfoFor(metricKey);
  const label = info?.label ?? metricKey;
  const showComparison = metric != null && metric.baseline != null && metric.delta_pct != null;

  const drillDownProps = onDrillDown
    ? {
        role: 'button' as const,
        tabIndex: 0,
        'aria-label': strings.metricTile.drillDownLabel(label),
        onClick: onDrillDown,
        onKeyDown: (event: ReactKeyboardEvent) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            onDrillDown();
          }
        },
      }
    : {};

  return (
    <div
      className={`relative rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4 ${
        onDrillDown ? 'cursor-pointer transition-colors hover:border-strong' : ''
      }`}
      {...drillDownProps}
    >
      {/* Absolutely positioned (not a flex row alongside the label) so the
          label stays a direct child of this container -- callers elsewhere in
          the codebase walk up from the label text via `.closest('div')` to
          reach the whole tile, a pattern an extra wrapping div would break. */}
      {/* Swallows clicks/keydowns before they reach the tile's own drill-down
          handler above -- otherwise activating the nested info button would
          also fire onDrillDown. */}
      <div className="absolute right-3 top-3" onClick={(event) => event.stopPropagation()}>
        <MetricInfoBadge metricKey={metricKey} />
      </div>
      <p className="pr-6 text-xs sm:text-sm font-medium text-ink-secondary">{label}</p>
      <p className="mt-1 sm:mt-2 text-lg sm:text-2xl font-bold tabular-nums text-ink">
        {formatValue(value, format)}
      </p>
      {sublabel && <p className="mt-1 text-xs text-ink-muted">{sublabel}</p>}
      {/* Item 1 (regression from a prior parity round): always rendered, even when
          `metric` is absent, so every tile in a grid reserves the same footer height
          as `Sparkline`'s own fixed `h-8` box -- `min-h-8` is what makes tiles without
          a `metric` prop (net_worth, total_assets, total_liabilities, ...) the same
          height as tiles that have one, with no per-grid CSS needed. */}
      <div className="mt-2 flex items-end justify-between gap-2 min-h-8">
        {metric && (
          <div className="flex flex-col gap-0.5">
            <DeltaBadge metricKey={metricKey} metric={metric} />
            {showComparison && (
              <p className="text-xs text-ink-muted">
                {strings.metricTile.baselineComparison(metric.delta_pct as number, metric.baseline_months)}
              </p>
            )}
          </div>
        )}
        {metric && <Sparkline metricKey={metricKey} metric={metric} />}
      </div>
    </div>
  );
}
