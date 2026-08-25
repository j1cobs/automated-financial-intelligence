/**
 * Home tab: the daily-check-in landing surface (PLAN.md's insight-first
 * dashboard work, §4 Q1/Q2). "Am I OK, and what changed?" -- the four
 * existing tabs are unchanged and serve as the "go deeper" layer this
 * reframes as drill-down, reached via the tab nav in `Dashboard.tsx`.
 */

import type { ReactNode } from 'react';
import { useHome } from '../lib/queries';
import { MetricTile } from './MetricTile';
import { TabSkeleton, ErrorState } from './LoadingState';
import { toneFor, polarityOf, directionOf, TONE_TOKENS, DIRECTION_GLYPH } from '../lib/polarity';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { gridProps, xAxisProps, yAxisProps, tooltipProps, CHART_MARGIN, positiveColor } from './chartTheme';

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

function InsightCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      {children}
    </div>
  );
}

function EmptyNote({ children }: { children: ReactNode }) {
  return <p className="mt-2 text-sm text-ink-muted">{children}</p>;
}

export function HomeTab() {
  const { data, isLoading, error, refetch } = useHome();

  if (isLoading) {
    return <TabSkeleton />;
  }

  if (error) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : 'An unexpected error occurred'}
        onRetry={() => void refetch()}
      />
    );
  }

  if (data?.net_worth_trend == null) {
    return (
      <div className="rounded-lg border border-hairline bg-surface-2 p-6">
        <p className="text-ink-secondary">No data available</p>
      </div>
    );
  }

  const trend = data.net_worth_trend;
  const latestNetWorth = trend.length > 0 ? trend[trend.length - 1].net_worth : null;
  const projection = data.cash_flow_projection;

  return (
    <div className="space-y-6">
      {/* Status row -- the "am I OK" answer at a glance. */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {latestNetWorth != null && <MetricTile metricKey="net_worth" value={latestNetWorth} />}
        <MetricTile metricKey="recurring_monthly_spend" value={data.recurring_monthly_spend} />
        {projection && (
          <MetricTile
            metricKey="projected_month_end_expenses"
            value={projection.projected_expenses}
            sublabel={`day ${projection.days_elapsed} of ${projection.days_in_month}`}
          />
        )}
      </div>

      <InsightCard title="Net Worth Trend">
        {trend.length >= 2 ? (
          <ResponsiveContainer width="100%" height={220} minWidth="100%">
            <LineChart data={trend} margin={CHART_MARGIN.default}>
              <CartesianGrid {...gridProps()} />
              <XAxis dataKey="date" {...xAxisProps()} />
              <YAxis {...yAxisProps()} tickFormatter={(value) => formatCurrency(value as number)} />
              <Tooltip {...tooltipProps()} formatter={(value) => formatCurrency(value as number)} />
              <Line
                type="monotone"
                dataKey="net_worth"
                stroke={positiveColor()}
                strokeWidth={2}
                dot={{ fill: positiveColor() }}
                name="Net Worth"
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <EmptyNote>
            History starts the day balance tracking shipped — check back after a few more days for a trend.
          </EmptyNote>
        )}
      </InsightCard>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <InsightCard title="Top Merchants (trailing 12 months)">
          {data.top_merchants.length === 0 ? (
            <EmptyNote>Not enough expense history yet.</EmptyNote>
          ) : (
            <ul className="mt-2 space-y-1.5">
              {data.top_merchants.map((row) => (
                <li key={row.description} className="flex items-center justify-between text-sm">
                  <span className="text-ink-secondary">{row.description}</span>
                  <span className="tabular-nums font-medium text-ink">{formatCurrency(row.amount)}</span>
                </li>
              ))}
            </ul>
          )}
        </InsightCard>

        <InsightCard title="Committed / Recurring Spend">
          {data.recurring_items.length === 0 ? (
            <EmptyNote>
              Nothing flagged recurring yet — mark a transaction recurring in the Transactions tab.
            </EmptyNote>
          ) : (
            <ul className="mt-2 space-y-1.5">
              {data.recurring_items.map((row) => (
                <li key={row.description} className="flex items-center justify-between text-sm">
                  <span className="text-ink-secondary">{row.description}</span>
                  <span className="tabular-nums font-medium text-ink">{formatCurrency(row.amount)}</span>
                </li>
              ))}
            </ul>
          )}
        </InsightCard>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <InsightCard title="Category Drift vs. Your Usual">
          {data.category_drift.length === 0 ? (
            <EmptyNote>Not enough history yet to compare this month.</EmptyNote>
          ) : (
            <ul className="mt-2 space-y-1.5">
              {data.category_drift.map((row) => {
                const tone = toneFor(row.drift_pct, polarityOf('category_spend'));
                const direction = directionOf(row.drift_pct);
                return (
                  <li key={row.category} className="flex items-center justify-between text-sm">
                    <span className="text-ink-secondary">{row.category}</span>
                    <span className="tabular-nums font-medium" style={{ color: TONE_TOKENS[tone].text }}>
                      {DIRECTION_GLYPH[direction]} {formatPercent(Math.abs(row.drift_pct))}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </InsightCard>

        <InsightCard title="Detected Subscriptions">
          {data.subscriptions.length === 0 ? (
            <EmptyNote>None detected in the trailing 6 months.</EmptyNote>
          ) : (
            <ul className="mt-2 space-y-1.5">
              {data.subscriptions.map((row) => (
                <li key={row.description} className="flex items-center justify-between text-sm">
                  <span className="text-ink-secondary">{row.description}</span>
                  <span className="tabular-nums font-medium text-ink">
                    {formatCurrency(row.average_amount)}/mo
                  </span>
                </li>
              ))}
            </ul>
          )}
        </InsightCard>
      </div>
    </div>
  );
}
