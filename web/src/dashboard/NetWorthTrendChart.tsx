/**
 * Financial Trends chart (Phase 23, retitled Phase 24): the former Home tab's
 * net-worth-history insight, now a self-contained component embedded in the
 * Overview tab in place of the old standalone Savings Rate Trend chart. Named
 * "Financial Trends" rather than "Net Worth Trend" since the Monthly tab
 * carries four different metrics, not just net worth. Purely presentational
 * -- the parent (`OverviewTab.tsx`) fetches via `useOverview()` and passes the
 * two trend arrays plus the month-over-month delta down as props.
 *
 * Two tabs share this one component instead of two separate charts:
 *  - Daily: one y-axis (every series is dollar-denominated) -- net worth,
 *    assets, liabilities, liquid cash.
 *  - Monthly: three y-axes -- dollars (net worth), percent (savings rate +
 *    credit utilization, which share a unit), and a count (emergency fund
 *    months). Defaults to Monthly since the daily snapshot history is
 *    currently sparse (the backing pipeline doesn't run every day yet).
 *
 * Every line stays mounted always (so it never disappears from the legend)
 * and toggles via Recharts' `<Line hide>` prop instead of conditional
 * rendering -- clicking a legend entry toggles its `dataKey` in a per-tab
 * `hiddenKeys` set. The Monthly tab seeds its set with the two "detail" lines
 * (credit utilization, emergency fund months) hidden by default, keeping the
 * default view to Net Worth + Savings Rate.
 */

import { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import type { NetWorthTrendDailyItem, NetWorthTrendMonthlyItem } from '../lib/types';
import {
  useChartTheme,
  categoricalColor,
  positiveColor,
  gridProps,
  xAxisProps,
  yAxisProps,
  tooltipProps,
  legendProps,
  CHART_MARGIN,
} from './chartTheme';

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatMonths(value: number): string {
  return `${value.toFixed(1)} months`;
}

type TrendTab = 'daily' | 'monthly';

/** Monthly tab's default-hidden lines: the two "detail" series, keyed by
 *  `dataKey` -- Net Worth and Savings Rate stay visible out of the box. */
const DEFAULT_HIDDEN_MONTHLY = new Set<string>(['credit_utilization_pct', 'emergency_fund_months']);
/** Daily tab shows all four lines by default. */
const DEFAULT_HIDDEN_DAILY = new Set<string>();

function TabPill({ active, onClick, children }: { active: boolean; onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
        active ? 'bg-surface-1 text-ink shadow-sm' : 'text-ink-muted hover:text-ink-secondary'
      }`}
    >
      {children}
    </button>
  );
}

interface NetWorthTrendChartProps {
  daily: NetWorthTrendDailyItem[];
  monthly: NetWorthTrendMonthlyItem[];
  netWorthMomDelta: number | null;
}

export function NetWorthTrendChart({ daily, monthly, netWorthMomDelta }: NetWorthTrendChartProps) {
  // Re-resolve chart colours (read from CSS vars) when the theme flips.
  useChartTheme();

  const [tab, setTab] = useState<TrendTab>('monthly');
  const [hiddenDaily, setHiddenDaily] = useState<Set<string>>(DEFAULT_HIDDEN_DAILY);
  const [hiddenMonthly, setHiddenMonthly] = useState<Set<string>>(DEFAULT_HIDDEN_MONTHLY);

  const hiddenKeys = tab === 'daily' ? hiddenDaily : hiddenMonthly;
  const setHiddenKeys = tab === 'daily' ? setHiddenDaily : setHiddenMonthly;

  function toggleKey(dataKey: string) {
    setHiddenKeys((prev) => {
      const next = new Set(prev);
      if (next.has(dataKey)) {
        next.delete(dataKey);
      } else {
        next.add(dataKey);
      }
      return next;
    });
  }

  function handleLegendClick(entry: { dataKey?: unknown }) {
    if (typeof entry.dataKey === 'string') {
      toggleKey(entry.dataKey);
    }
  }

  return (
    <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base sm:text-lg font-semibold text-ink">Financial Trends</h3>
        <div className="inline-flex rounded-full border border-hairline bg-surface-2 p-1">
          <TabPill active={tab === 'daily'} onClick={() => setTab('daily')}>
            Daily
          </TabPill>
          <TabPill active={tab === 'monthly'} onClick={() => setTab('monthly')}>
            Monthly
          </TabPill>
        </div>
      </div>

      {tab === 'monthly' && netWorthMomDelta != null && (
        <p className="mb-2 text-sm tabular-nums font-medium text-ink-secondary">
          {netWorthMomDelta >= 0 ? '+' : '-'}
          {formatCurrency(Math.abs(netWorthMomDelta))} since last month
        </p>
      )}

      {tab === 'daily' ? (
        daily.length > 0 ? (
          <ResponsiveContainer width="100%" height={280} minWidth="100%">
            <LineChart data={daily} margin={CHART_MARGIN.default}>
              <CartesianGrid {...gridProps()} />
              <XAxis dataKey="date" {...xAxisProps()} />
              <YAxis {...yAxisProps(64)} tickFormatter={(value) => formatCurrency(value as number)} />
              <Tooltip {...tooltipProps()} formatter={(value) => formatCurrency(value as number)} />
              <Legend {...legendProps()} onClick={handleLegendClick} />
              <Line
                type="monotone"
                dataKey="net_worth"
                name="Net Worth"
                stroke={positiveColor()}
                strokeWidth={2}
                dot={false}
                hide={hiddenKeys.has('net_worth')}
              />
              <Line
                type="monotone"
                dataKey="assets"
                name="Total Assets"
                stroke={categoricalColor(0)}
                strokeWidth={2}
                dot={false}
                hide={hiddenKeys.has('assets')}
              />
              <Line
                type="monotone"
                dataKey="liabilities"
                name="Total Liabilities"
                stroke={categoricalColor(1)}
                strokeWidth={2}
                dot={false}
                hide={hiddenKeys.has('liabilities')}
              />
              <Line
                type="monotone"
                dataKey="liquid_cash"
                name="Liquid Cash"
                stroke={categoricalColor(2)}
                strokeWidth={2}
                dot={false}
                hide={hiddenKeys.has('liquid_cash')}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="mt-2 text-sm text-ink-muted">
            History starts the day balance tracking shipped — check back after a few more days for a trend.
          </p>
        )
      ) : monthly.length > 0 ? (
        <ResponsiveContainer width="100%" height={280} minWidth="100%">
          <LineChart data={monthly} margin={CHART_MARGIN.wide}>
            <CartesianGrid {...gridProps()} />
            <XAxis dataKey="month" {...xAxisProps()} />
            <YAxis
              yAxisId="dollar"
              {...yAxisProps(64)}
              tickFormatter={(value) => formatCurrency(value as number)}
            />
            <YAxis
              yAxisId="percent"
              orientation="right"
              {...yAxisProps(56)}
              tickFormatter={(value) => formatPercent(value as number)}
            />
            <YAxis
              yAxisId="months"
              orientation="right"
              {...yAxisProps(64)}
              tickFormatter={(value) => formatMonths(value as number)}
            />
            <Tooltip
              {...tooltipProps()}
              formatter={(value, name) => {
                const numeric = value as number;
                if (name === 'Savings Rate' || name === 'Credit Utilization %') {
                  return formatPercent(numeric);
                }
                if (name === 'Emergency Fund Months') {
                  return formatMonths(numeric);
                }
                return formatCurrency(numeric);
              }}
            />
            <Legend {...legendProps()} onClick={handleLegendClick} />
            <Line
              yAxisId="dollar"
              type="monotone"
              dataKey="net_worth"
              name="Net Worth"
              stroke={positiveColor()}
              strokeWidth={2}
              dot={false}
              hide={hiddenKeys.has('net_worth')}
            />
            <Line
              yAxisId="percent"
              type="monotone"
              dataKey="savings_rate"
              name="Savings Rate"
              stroke={categoricalColor(0)}
              strokeWidth={2}
              dot={false}
              connectNulls={false}
              hide={hiddenKeys.has('savings_rate')}
            />
            <Line
              yAxisId="percent"
              type="monotone"
              dataKey="credit_utilization_pct"
              name="Credit Utilization %"
              stroke={categoricalColor(1)}
              strokeWidth={2}
              dot={false}
              connectNulls={false}
              hide={hiddenKeys.has('credit_utilization_pct')}
            />
            <Line
              yAxisId="months"
              type="monotone"
              dataKey="emergency_fund_months"
              name="Emergency Fund Months"
              stroke={categoricalColor(2)}
              strokeWidth={2}
              dot={false}
              connectNulls={false}
              hide={hiddenKeys.has('emergency_fund_months')}
            />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <p className="mt-2 text-sm text-ink-muted">
          Not enough monthly history yet to show a trend — check back after a full month of data.
        </p>
      )}
    </div>
  );
}
