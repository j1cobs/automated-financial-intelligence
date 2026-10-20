/**
 * Financial Trends chart (Phase 23, retitled Phase 24): the former Home tab's
 * net-worth-history insight, now a self-contained component embedded in the
 * Overview tab in place of the old standalone Savings Rate Trend chart. Named
 * "Financial Trends" rather than "Net Worth Trend" since it carries four
 * different metrics, not just net worth. Purely presentational -- the parent
 * (`OverviewTab.tsx`) fetches via `useOverview()` and passes the two trend
 * arrays plus the month-over-month delta down as props.
 *
 * Three flat tabs, one axis (unit) each -- overlaying dollars, percent and a
 * month-count on one shared axis (an earlier version of this chart did, via 3
 * simultaneous y-axes) makes a chart that LOOKS combined but isn't actually
 * comparable: a dollar *level* and a percentage *rate* don't share a
 * meaningful scale just because they're both plotted against time, and an
 * axis for a currently-hidden line still rendered, cluttering the chart for
 * no reason. Splitting by unit keeps every axis honest instead:
 *  - Daily: net worth, assets, liabilities, liquid cash -- all dollars.
 *  - Net Worth: monthly net worth alone -- dollars.
 *  - Rates: monthly savings rate + credit utilization -- both genuinely
 *    percentages, a real shared unit, no normalization needed.
 * Emergency Fund Months is intentionally NOT plotted here -- it already has
 * its own live-value card (Overview tab's "Emergency Fund"), and a month-count
 * has no home among the other three units without reintroducing the
 * multi-axis problem this split exists to avoid.
 *
 * Every line stays mounted always (so it never disappears from the legend)
 * and toggles via Recharts' `<Line hide>` prop instead of conditional
 * rendering -- clicking a legend entry toggles its `dataKey` in a per-tab
 * `hiddenKeys` set.
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

type TrendTab = 'daily' | 'net_worth' | 'rates';

/** Every tab shows all of its (small) line set by default -- unlike the old
 *  combined Monthly tab, none of these has enough lines to need a default
 *  decluttering. */
const DEFAULT_HIDDEN: Record<TrendTab, Set<string>> = {
  daily: new Set(),
  net_worth: new Set(),
  rates: new Set(),
};

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

  const [tab, setTab] = useState<TrendTab>('net_worth');
  const [hidden, setHidden] = useState<Record<TrendTab, Set<string>>>(DEFAULT_HIDDEN);

  const hiddenKeys = hidden[tab];

  function toggleKey(dataKey: string) {
    setHidden((prev) => {
      const next = new Set(prev[tab]);
      if (next.has(dataKey)) {
        next.delete(dataKey);
      } else {
        next.add(dataKey);
      }
      return { ...prev, [tab]: next };
    });
  }

  function handleLegendClick(entry: { dataKey?: unknown }) {
    if (typeof entry.dataKey === 'string') {
      toggleKey(entry.dataKey);
    }
  }

  const noMonthlyHistory = (
    <p className="mt-2 text-sm text-ink-muted">
      Not enough monthly history yet to show a trend — check back after a full month of data.
    </p>
  );

  return (
    <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base sm:text-lg font-semibold text-ink">Financial Trends</h3>
        <div className="inline-flex rounded-full border border-hairline bg-surface-2 p-1">
          <TabPill active={tab === 'daily'} onClick={() => setTab('daily')}>
            Daily
          </TabPill>
          <TabPill active={tab === 'net_worth'} onClick={() => setTab('net_worth')}>
            Net Worth
          </TabPill>
          <TabPill active={tab === 'rates'} onClick={() => setTab('rates')}>
            Rates
          </TabPill>
        </div>
      </div>

      {tab === 'net_worth' && netWorthMomDelta != null && (
        <p className="mb-2 text-sm tabular-nums font-medium text-ink-secondary">
          {netWorthMomDelta >= 0 ? '+' : '-'}
          {formatCurrency(Math.abs(netWorthMomDelta))} since last month
        </p>
      )}

      {tab === 'daily' &&
        (daily.length > 0 ? (
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
        ))}

      {tab === 'net_worth' &&
        (monthly.length > 0 ? (
          <ResponsiveContainer width="100%" height={280} minWidth="100%">
            <LineChart data={monthly} margin={CHART_MARGIN.default}>
              <CartesianGrid {...gridProps()} />
              <XAxis dataKey="month" {...xAxisProps()} />
              <YAxis {...yAxisProps(64)} tickFormatter={(value) => formatCurrency(value as number)} />
              <Tooltip {...tooltipProps()} formatter={(value) => formatCurrency(value as number)} />
              <Line
                type="monotone"
                dataKey="net_worth"
                name="Net Worth"
                stroke={positiveColor()}
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          noMonthlyHistory
        ))}

      {tab === 'rates' &&
        (monthly.length > 0 ? (
          <ResponsiveContainer width="100%" height={280} minWidth="100%">
            <LineChart data={monthly} margin={CHART_MARGIN.default}>
              <CartesianGrid {...gridProps()} />
              <XAxis dataKey="month" {...xAxisProps()} />
              <YAxis {...yAxisProps(56)} tickFormatter={(value) => formatPercent(value as number)} />
              <Tooltip {...tooltipProps()} formatter={(value) => formatPercent(value as number)} />
              <Legend {...legendProps()} onClick={handleLegendClick} />
              <Line
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
                type="monotone"
                dataKey="credit_utilization_pct"
                name="Credit Utilization %"
                stroke={categoricalColor(1)}
                strokeWidth={2}
                dot={false}
                connectNulls={false}
                hide={hiddenKeys.has('credit_utilization_pct')}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          noMonthlyHistory
        ))}
    </div>
  );
}
