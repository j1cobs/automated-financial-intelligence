/**
 * Forward cash-flow forecast (Phase 32), at the top of the Budget tab.
 *
 * Form: change over time, two series, both in dollars — a line chart on a
 * SINGLE axis. The two lines answer different questions about the same
 * quantity:
 *
 *   Projected — what will probably happen (recurring streams + a trailing
 *     median per category).
 *   If you hit every cap — the same, with each category held to its budget.
 *
 * Carrying both is the whole point: the gap between them is the value of
 * sticking to budget. Forecasting from caps alone would project a world in
 * which you hit every target, which is an aspiration rather than a forecast.
 *
 * Colour comes from `chartTheme`'s categorical order, not from new hues, so the
 * already-validated palette applies unchanged. Two series means a legend is
 * always present, and the dashed stroke gives the budget line a second,
 * non-colour encoding for the colour-vision case.
 */

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts';
import type { TooltipContentProps } from 'recharts';
import { useForecast } from '../lib/queries';
import {
  useChartTheme,
  categoricalColor,
  gridProps,
  xAxisProps,
  yAxisProps,
  legendProps,
  activeDotProps,
  axisColor,
  LINE_PROPS,
  CHART_MARGIN,
} from './chartTheme';

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);
}

function formatMonth(period: string): string {
  const [year, month] = period.split('-').map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString('en-US', {
    month: 'short',
    year: '2-digit',
  });
}

const PROJECTED_LABEL = 'Projected';
const BUDGET_LABEL = 'If you hit every cap';

function ForecastTooltip({ active, payload, label }: Partial<TooltipContentProps<number, string>>) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-md border border-hairline bg-surface-1 p-2 text-xs shadow-sm">
      <p className="mb-1 font-semibold text-ink">{formatMonth(String(label))}</p>
      {payload.map((entry) => (
        <p key={String(entry.name)} className="flex items-center gap-2 text-ink-secondary">
          <span
            aria-hidden="true"
            className="inline-block h-2 w-2 shrink-0 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          {entry.name}
          <span className="ml-auto tabular-nums text-ink">{formatCurrency(Number(entry.value))}</span>
        </p>
      ))}
    </div>
  );
}

export function ForecastChart() {
  const { data, isPending } = useForecast();
  useChartTheme(); // re-render when the theme flips

  if (isPending || !data) return null;

  // Below three complete months a median is a guess, so the API returns no
  // rows. Say that plainly rather than drawing a line nobody should trust.
  if (!data.has_enough_history) {
    return (
      <div className="rounded-lg border border-hairline bg-surface-1 p-4">
        <h3 className="text-base font-semibold text-ink">Forecast</h3>
        <p className="mt-1 text-sm text-ink-muted">
          Building history — {data.months_of_history} complete month
          {data.months_of_history === 1 ? '' : 's'} so far. A projection needs at least three.
        </p>
      </div>
    );
  }

  const projectedColor = categoricalColor(0);
  const budgetColor = categoricalColor(1);

  return (
    <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-base font-semibold text-ink">Forecast</h3>
        <span className="text-xs text-ink-muted tabular-nums">
          From {formatCurrency(data.starting_balance)} on hand
        </span>
      </div>
      <p className="mb-2 text-xs text-ink-muted">
        Spendable cash only, projected from your own history.
        {!data.has_recurring_data &&
          ' No recurring charges detected yet, so this is trailing averages alone.'}
      </p>

      <div className="h-64 w-full sm:h-80">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data.rows} margin={CHART_MARGIN.default}>
            <CartesianGrid {...gridProps()} />
            <XAxis {...xAxisProps()} dataKey="month" tickFormatter={formatMonth} />
            <YAxis {...yAxisProps(72)} tickFormatter={(value: number) => formatCurrency(value)} />
            {/* Zero is the line that matters on a balance forecast: crossing it
                means running out, which a gridline alone does not announce. */}
            <ReferenceLine y={0} stroke={axisColor()} strokeWidth={1} />
            <Tooltip content={<ForecastTooltip />} cursor={{ strokeDasharray: '3 3' }} />
            <Legend {...legendProps()} />
            <Line
              {...LINE_PROPS}
              dataKey="projected_balance"
              name={PROJECTED_LABEL}
              stroke={projectedColor}
              activeDot={activeDotProps()}
              // Recharts animates a line in by driving stroke-dasharray, which
              // both fights the dashed budget line below and is motion nobody
              // asked for on a planning chart.
              isAnimationActive={false}
            />
            <Line
              {...LINE_PROPS}
              dataKey="budget_balance"
              name={BUDGET_LABEL}
              stroke={budgetColor}
              // Second, non-colour encoding: the two lines stay tellable apart
              // without relying on hue.
              strokeDasharray="5 4"
              activeDot={activeDotProps()}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
