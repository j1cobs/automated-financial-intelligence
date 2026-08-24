import { useState, type ReactNode } from 'react';
import { useOverview } from '../lib/queries';
import { useSetCreditLimit } from '../lib/mutations';
import { useFilters } from '../lib/FilterContext';
import type { PieLabelRenderProps, TooltipContentProps } from 'recharts';
import type {
  CreditUtilizationItem,
  MonthOverMonthItem,
  OwnerBalanceItem,
  TopCategoryItem,
} from '../lib/types';
import { MetricTile, MetricInfoBadge } from './MetricTile';
import { strings } from '../lib/strings';
import {
  LineChart,
  Line,
  PieChart,
  Pie,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from 'recharts';
import {
  useChartTheme,
  categoricalColor,
  categoricalScale,
  incomeColor,
  expenseColor,
  gridProps,
  xAxisProps,
  yAxisProps,
  tooltipProps,
  legendProps,
  referenceLineProps,
  surfaceGapProps,
  CHART_MARGIN,
  BAR_MAX_SIZE,
  BAR_RADIUS_HORIZONTAL,
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

function OwnerBalancesTooltip({ active, payload }: Partial<TooltipContentProps<number, string>>) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }
  const row = payload[0]?.payload as OwnerBalanceItem | undefined;
  if (!row) {
    return null;
  }
  return (
    <div className="rounded-md border border-hairline bg-surface-1 p-2 text-xs shadow-sm sm:text-sm">
      <p className="mb-1 font-semibold text-ink">{row.owner}</p>
      {row.accounts.map((account) => (
        <p key={account.account_name} className="text-ink-secondary">
          {account.account_name} ({account.type}): {formatCurrency(account.value)}
        </p>
      ))}
    </div>
  );
}

/**
 * Card wrapper matching the chart cards below — used for non-chart content
 * (credit utilisation, warnings, the emergency-fund meter) so the page reads
 * as one system.
 */
function Card({
  title,
  caption,
  metricKey,
  children,
}: {
  title: string;
  caption?: string;
  /** Optional metricInfo key -- renders the Fix 13 tooltip badge beside the title. */
  metricKey?: string;
  children: ReactNode;
}) {
  return (
    <div className="relative rounded-lg border border-hairline bg-surface-1 p-3 sm:p-6">
      {/* Absolutely positioned, not a flex row beside the title -- keeps the
          title a direct child of this container so `heading.closest('div')`
          (used throughout this file's tests) still reaches the whole card. */}
      {metricKey && (
        <div className="absolute right-3 top-3 sm:right-6 sm:top-6">
          <MetricInfoBadge metricKey={metricKey} />
        </div>
      )}
      <h3 className="pr-6 text-base sm:text-lg font-semibold text-ink">{title}</h3>
      {caption && <p className="mt-1 text-xs text-ink-muted">{caption}</p>}
      <div className="mt-4">{children}</div>
    </div>
  );
}

type MeterTone = 'pos' | 'warn' | 'serious' | 'neutral';

const METER_FILL_CLASS: Record<MeterTone, string> = {
  pos: 'bg-pos',
  warn: 'bg-warn',
  serious: 'bg-serious',
  neutral: 'bg-neutral',
};

/**
 * A same-ramp meter (dataviz `marks-and-anatomy.md`): the fill carries
 * severity, the unfilled track is a lighter neutral step. Color is never the
 * only signal — callers pass a text label alongside.
 */
function Meter({ pct, tone }: { pct: number; tone: MeterTone }) {
  const clamped = Math.min(Math.max(pct, 0), 1);
  return (
    <div
      className="h-2 w-full overflow-hidden rounded-full bg-surface-3"
      role="progressbar"
      aria-valuenow={Math.round(clamped * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={`h-full rounded-full ${METER_FILL_CLASS[tone]}`}
        style={{ width: `${clamped * 100}%` }}
      />
    </div>
  );
}

function creditTone(pct: number): MeterTone {
  if (pct >= 0.9) return 'serious';
  if (pct >= 0.7) return 'warn';
  return 'pos';
}

function emergencyFundTone(months: number): MeterTone {
  if (months >= 6) return 'pos';
  if (months >= 3) return 'warn';
  return 'serious';
}

/** Per-card row: "{account} — {owner} — $current / $limit (n% used)". Mirrors
 * `app/dashboard.py:604-627`. A null limit shows "$X owed — no credit limit
 * set" with no bar, since there's nothing to measure against. */
function CreditUtilizationRow({ item }: { item: CreditUtilizationItem }) {
  const owner = item.owner_name ?? '—';
  if (item.limit == null || item.pct == null) {
    return (
      <div className="py-2">
        <p className="text-sm text-ink">
          {item.account_name} — {owner} — {formatCurrency(item.current)} owed — no credit limit set
        </p>
      </div>
    );
  }
  const tone = creditTone(item.pct);
  return (
    <div className="py-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 text-sm text-ink">
        <span>
          {item.account_name} — {owner}
        </span>
        <span className="text-ink-secondary">
          {formatCurrency(item.current)} / {formatCurrency(item.limit)} ({formatPercent(item.pct)} used)
          {item.is_manual && <span className="text-ink-muted"> · manually set limit</span>}
        </span>
      </div>
      <div className="mt-1">
        <Meter pct={item.pct} tone={tone} />
      </div>
    </div>
  );
}

/** Collapsible editor wired to `useSetCreditLimit()` (previously unused).
 * Mirrors `app/dashboard.py:630-675`'s data-editor + save button, one row
 * per card, keyed on `account_key`. */
function CreditLimitEditor({ items }: { items: CreditUtilizationItem[] }) {
  const { mutate, isPending } = useSetCreditLimit();
  const [inputs, setInputs] = useState<Record<string, string>>({});

  function valueFor(item: CreditUtilizationItem): string {
    return inputs[item.account_key] ?? (item.limit != null ? String(item.limit) : '');
  }

  function save(item: CreditUtilizationItem) {
    const raw = valueFor(item).trim();
    if (raw === '') {
      mutate({ accountKey: item.account_key, limit: null });
      return;
    }
    const parsed = Number(raw);
    if (Number.isNaN(parsed)) return;
    mutate({ accountKey: item.account_key, limit: parsed });
  }

  return (
    <details className="mt-4 rounded-md border border-hairline bg-surface-2 p-3">
      <summary className="cursor-pointer text-sm font-semibold text-ink">Edit credit limits</summary>
      <div className="mt-3 space-y-3">
        {items.map((item) => (
          <div key={item.account_key} className="flex flex-wrap items-center gap-2">
            <label htmlFor={`credit-limit-${item.account_key}`} className="min-w-0 flex-1 text-sm text-ink">
              {item.account_name} — {item.owner_name ?? '—'}
            </label>
            <input
              id={`credit-limit-${item.account_key}`}
              type="number"
              min={0}
              step="1"
              aria-label={`Credit limit for ${item.account_name}`}
              className="w-28 rounded border border-strong bg-surface-1 px-2 py-1 text-sm text-ink"
              value={valueFor(item)}
              onChange={(e) => setInputs((prev) => ({ ...prev, [item.account_key]: e.target.value }))}
            />
            <button
              type="button"
              disabled={isPending}
              onClick={() => save(item)}
              className="rounded bg-cat-1 px-3 py-1 text-sm font-medium text-white disabled:opacity-50"
            >
              Save
            </button>
          </div>
        ))}
      </div>
    </details>
  );
}

/** Pivots the API's long `{category, period, amount}` rows into one wide row
 * per category so a single grouped `<BarChart>` can plot both series. */
function buildMonthOverMonthRows(
  items: MonthOverMonthItem[],
): { category: string; this_month: number; last_month: number }[] {
  const byCategory = new Map<string, { this_month: number; last_month: number }>();
  for (const item of items) {
    const entry = byCategory.get(item.category) ?? { this_month: 0, last_month: 0 };
    if (item.period === 'this_month') {
      entry.this_month = item.amount;
    } else if (item.period === 'last_month') {
      entry.last_month = item.amount;
    }
    byCategory.set(item.category, entry);
  }
  return Array.from(byCategory.entries())
    .map(([category, amounts]) => ({ category, ...amounts }))
    .sort((a, b) => b.this_month - a.this_month);
}

export function OverviewTab() {
  const { data, isLoading, error } = useOverview();
  const { filters, patchFilters } = useFilters();
  // Re-render charts (their colours are resolved from CSS vars in JS) when the theme flips.
  useChartTheme();

  // Cross-filtering (Fix 14): clicking a category bar adds it to the active
  // filters via the shared FilterContext -- no separate filter mechanism.
  // Idempotent: clicking an already-active category is a no-op, not a toggle
  // (removal is the FilterBar chip's job).
  function addCategoryFilter(category: string) {
    const current = filters.categories ?? [];
    if (current.includes(category)) return;
    patchFilters({ categories: [...current, category] });
  }

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-hairline border-t-cat-1"></div>
        <p className="mt-4 text-ink-secondary">Loading overview...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-strong bg-surface-2 p-6">
        <h3 className="text-lg font-semibold text-neg-text">Error loading overview</h3>
        <p className="mt-2 text-ink-secondary">
          {error instanceof Error ? error.message : 'An unexpected error occurred'}
        </p>
      </div>
    );
  }

  if (data?.net_worth == null || data?.overview == null) {
    return (
      <div className="rounded-lg border border-hairline bg-surface-2 p-6">
        <p className="text-ink-secondary">No data available</p>
      </div>
    );
  }

  const nw = data.net_worth;
  const ov = data.overview;
  const hiddenSavingsMonths = ov.savings_rate_trend.filter((point) => point.savings_rate === null).length;
  // These three tiles average only whole calendar months, so say which window they cover —
  // otherwise "Monthly Expenses" is a number with no stated basis.
  const monthlyWindow =
    ov.complete_months === 0
      ? 'not enough complete months'
      : `avg of ${ov.complete_months} complete ${ov.complete_months === 1 ? 'month' : 'months'}`;
  const dormantCount = nw.dormant_accounts.length;
  const monthOverMonthRows = buildMonthOverMonthRows(ov.month_over_month);
  const sortedIncomeBreakdown = [...ov.income_breakdown].sort((a, b) => b.amount - a.amount);

  return (
    <div className="space-y-6">
      {/* KPI Tiles -- MetricTile (Fix 12/13): value + baseline comparison +
          sparkline where the API provides it, plus a hover/tap tooltip for
          every metric from `metricInfo.ts`. */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricTile metricKey="net_worth" value={nw.net_worth} />
        <MetricTile metricKey="total_assets" value={nw.total_assets} />
        <MetricTile metricKey="total_liabilities" value={nw.total_liabilities} />
        <MetricTile
          metricKey="savings_rate"
          value={ov.savings_rate}
          format="percent"
          metric={ov.metrics.savings_rate}
        />
      </div>

      {/* Duplicate-account warning — mirrors app/dashboard.py:537-543 */}
      {nw.forked_accounts.length > 0 && (
        <div className="rounded-lg border border-strong bg-surface-2 p-3 sm:p-6">
          <h3 className="font-semibold text-sm sm:text-base text-warn-text">
            These accounts appear more than once
          </h3>
          <p className="mt-2 text-sm text-ink-secondary">{nw.forked_accounts.join(', ')}</p>
        </div>
      )}

      {/* Income and Expenses Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <MetricTile
          metricKey="avg_monthly_income"
          value={ov.avg_monthly_income}
          sublabel={monthlyWindow}
          metric={ov.metrics.avg_monthly_income}
        />
        <MetricTile
          metricKey="avg_monthly_expense"
          value={ov.avg_monthly_expense}
          sublabel={monthlyWindow}
          metric={ov.metrics.avg_monthly_expense}
        />
        <MetricTile
          metricKey="avg_monthly_net"
          value={ov.avg_monthly_net}
          sublabel={monthlyWindow}
          metric={ov.metrics.avg_monthly_net}
        />
      </div>

      {/* Savings Rate Trend Chart */}
      {ov?.savings_rate_trend && ov.savings_rate_trend.length > 0 && (
        <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-6">
          <h3 className="mb-4 text-base sm:text-lg font-semibold text-ink">Savings Rate Trend</h3>
          <ResponsiveContainer width="100%" height={250} minWidth="100%">
            <LineChart data={ov.savings_rate_trend} margin={CHART_MARGIN.default}>
              <CartesianGrid {...gridProps()} />
              <XAxis dataKey="month" {...xAxisProps()} />
              <YAxis
                {...yAxisProps()}
                tickFormatter={(value) => formatPercent(value)}
                domain={[-1, 1]}
                allowDataOverflow={true}
              />
              <Tooltip {...tooltipProps()} formatter={(value) => formatPercent(value as number)} />
              <ReferenceLine y={0.2} {...referenceLineProps()} strokeDasharray="4 4" label="Target 20%" />
              <Line
                type="monotone"
                dataKey="savings_rate"
                stroke={categoricalColor(0)}
                strokeWidth={2}
                dot={{ fill: categoricalColor(0) }}
                name="Savings Rate"
                connectNulls={false}
              />
            </LineChart>
          </ResponsiveContainer>
          {hiddenSavingsMonths > 0 && (
            <p className="mt-2 text-xs text-ink-muted">
              {hiddenSavingsMonths} {hiddenSavingsMonths === 1 ? 'month' : 'months'} hidden — no recorded
              income.
            </p>
          )}
        </div>
      )}

      {/* Asset Mix and Owner Balances */}
      <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
        {/* Asset Mix Pie Chart */}
        {nw?.asset_mix && nw.asset_mix.length > 0 && (
          <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-6">
            <h3 className="mb-4 text-base sm:text-lg font-semibold text-ink">Asset Mix</h3>
            <ResponsiveContainer width="100%" height={250} minWidth="100%">
              <PieChart>
                <Pie
                  data={nw.asset_mix}
                  dataKey="balance"
                  nameKey="subtype_label"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  label={(props: PieLabelRenderProps) => {
                    const entry = props.payload as unknown as { subtype_label: string; percent?: number };
                    const percent = (props as unknown as { percent?: number }).percent ?? 0;
                    return `${entry.subtype_label} ${(percent * 100).toFixed(0)}%`;
                  }}
                >
                  {nw.asset_mix.map((_, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={categoricalScale(nw.asset_mix.length)[index]}
                      {...surfaceGapProps()}
                    />
                  ))}
                </Pie>
                <Tooltip {...tooltipProps()} formatter={(value) => formatCurrency(value as number)} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Owner Balances Bar Chart */}
        {nw?.owner_balances && nw.owner_balances.length > 0 && (
          <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-6">
            <h3 className="mb-4 text-base sm:text-lg font-semibold text-ink">Owner Balances</h3>
            <ResponsiveContainer width="100%" height={250} minWidth="100%">
              <BarChart data={nw.owner_balances} margin={CHART_MARGIN.default}>
                <CartesianGrid {...gridProps()} />
                <XAxis dataKey="owner" {...xAxisProps()} />
                <YAxis {...yAxisProps()} tickFormatter={(value) => formatCurrency(value)} />
                <Tooltip content={<OwnerBalancesTooltip />} />
                <Legend {...legendProps()} />
                <ReferenceLine y={0} {...referenceLineProps()} />
                <Bar
                  dataKey="depository"
                  stackId="a"
                  fill={categoricalColor(0)}
                  name="Depository"
                  {...surfaceGapProps()}
                />
                <Bar
                  dataKey="investment"
                  stackId="a"
                  fill={categoricalColor(1)}
                  name="Investment"
                  {...surfaceGapProps()}
                />
                <Bar
                  dataKey="credit"
                  stackId="a"
                  fill={categoricalColor(7)}
                  name="Credit"
                  {...surfaceGapProps()}
                />
                {nw.owner_balances.some((row) => row.other !== 0) && (
                  <Bar
                    dataKey="other"
                    stackId="a"
                    fill={categoricalColor(6)}
                    name="Other"
                    {...surfaceGapProps()}
                  />
                )}
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Credit Utilization + limit editor — mirrors app/dashboard.py:604-675 */}
      {nw.credit_utilization.length > 0 && (
        <Card title="Credit Utilization" caption="Current balance against each card's limit.">
          <div className="divide-y divide-hairline">
            {nw.credit_utilization.map((item) => (
              <CreditUtilizationRow key={item.account_key} item={item} />
            ))}
          </div>
          <CreditLimitEditor items={nw.credit_utilization} />
        </Card>
      )}

      {/* Top Categories (horizontal, sorted — app/dashboard.py:865-889) and
          Month-over-month by category (app/dashboard.py:891-912) */}
      <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
        {ov?.top_categories && ov.top_categories.length > 0 && (
          <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-6">
            <h3 className="mb-1 text-base sm:text-lg font-semibold text-ink">Top Expense Categories</h3>
            <p className="mb-4 text-xs text-ink-muted">{strings.crossFilter.categoryHint}</p>
            <ResponsiveContainer
              width="100%"
              height={Math.max(250, ov.top_categories.length * 32)}
              minWidth="100%"
            >
              <BarChart data={ov.top_categories} layout="vertical" margin={CHART_MARGIN.default}>
                <CartesianGrid {...gridProps()} />
                <XAxis type="number" {...xAxisProps()} tickFormatter={(value) => formatCurrency(value)} />
                <YAxis dataKey="category" type="category" {...yAxisProps(96)} />
                <Tooltip {...tooltipProps()} formatter={(value) => formatCurrency(value as number)} />
                <Bar
                  dataKey="amount"
                  fill={expenseColor()}
                  name="Amount"
                  maxBarSize={BAR_MAX_SIZE}
                  radius={BAR_RADIUS_HORIZONTAL}
                  cursor="pointer"
                  onClick={(entry) => addCategoryFilter((entry.payload as TopCategoryItem).category)}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {monthOverMonthRows.length > 0 && (
          <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-6">
            <h3 className="mb-4 text-base sm:text-lg font-semibold text-ink">Month-over-Month by Category</h3>
            <ResponsiveContainer
              width="100%"
              height={Math.max(250, monthOverMonthRows.length * 32)}
              minWidth="100%"
            >
              <BarChart data={monthOverMonthRows} layout="vertical" margin={CHART_MARGIN.default}>
                <CartesianGrid {...gridProps()} />
                <XAxis type="number" {...xAxisProps()} tickFormatter={(value) => formatCurrency(value)} />
                <YAxis dataKey="category" type="category" {...yAxisProps(96)} />
                <Tooltip {...tooltipProps()} formatter={(value) => formatCurrency(value as number)} />
                <Legend {...legendProps()} />
                <Bar
                  dataKey="last_month"
                  name="Last month"
                  fill={categoricalColor(1)}
                  maxBarSize={BAR_MAX_SIZE}
                  radius={BAR_RADIUS_HORIZONTAL}
                />
                <Bar
                  dataKey="this_month"
                  name="This month"
                  fill={categoricalColor(0)}
                  maxBarSize={BAR_MAX_SIZE}
                  radius={BAR_RADIUS_HORIZONTAL}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Emergency fund progress + Income sources — app/dashboard.py:914-959 */}
      <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
        {ov.emergency_fund_months !== null && (
          <Card
            title="Emergency Fund"
            caption="Liquid savings ÷ average monthly expenses."
            metricKey="emergency_fund_months"
          >
            <p className="text-2xl font-bold text-ink">{ov.emergency_fund_months.toFixed(1)} months</p>
            <div className="mt-3">
              <Meter pct={ov.emergency_fund_months / 6} tone={emergencyFundTone(ov.emergency_fund_months)} />
            </div>
            <p className="mt-2 text-xs text-ink-muted">Goal: 6 months of expenses covered.</p>
          </Card>
        )}

        {sortedIncomeBreakdown.length > 0 && (
          <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-6">
            <h3 className="mb-4 text-base sm:text-lg font-semibold text-ink">Income Sources</h3>
            <ResponsiveContainer
              width="100%"
              height={Math.max(250, sortedIncomeBreakdown.length * 32)}
              minWidth="100%"
            >
              <BarChart data={sortedIncomeBreakdown} layout="vertical" margin={CHART_MARGIN.default}>
                <CartesianGrid {...gridProps()} />
                <XAxis type="number" {...xAxisProps()} tickFormatter={(value) => formatCurrency(value)} />
                <YAxis dataKey="description" type="category" {...yAxisProps(96)} />
                <Tooltip {...tooltipProps()} formatter={(value) => formatCurrency(value as number)} />
                <Bar
                  dataKey="amount"
                  fill={incomeColor()}
                  name="Income"
                  maxBarSize={BAR_MAX_SIZE}
                  radius={BAR_RADIUS_HORIZONTAL}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Additional Metrics */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <MetricTile metricKey="flagged_count" value={ov.flagged_count} format="number" />
        {ov.avg_weekly_expense > 0 && (
          <MetricTile metricKey="avg_weekly_expense" value={ov.avg_weekly_expense} />
        )}
        {ov.avg_weekly_income > 0 && (
          <MetricTile metricKey="avg_weekly_income" value={ov.avg_weekly_income} />
        )}
      </div>

      {/* Sync Health Warning */}
      {nw?.stale_accounts && nw.stale_accounts.length > 0 && (
        <div className="rounded-lg border border-strong bg-surface-2 p-3 sm:p-6">
          <h3 className="font-semibold text-sm sm:text-base text-warn-text">Balances may be out of date</h3>
          <div className="mt-2 space-y-1">
            {nw.stale_accounts.map((account) => (
              <p key={account.account_key} className="text-sm text-ink-secondary">
                {account.account_name} — balance last refreshed {account.days_stale} days ago
              </p>
            ))}
          </div>
          <p className="mt-2 text-xs text-ink-muted">
            This usually means the Plaid connection for these accounts needs to be repaired.
          </p>
        </div>
      )}

      {/* Dormant Accounts */}
      {nw?.dormant_accounts && nw.dormant_accounts.length > 0 && (
        <details className="rounded-lg border border-hairline bg-surface-2 p-3 sm:p-6">
          <summary className="cursor-pointer font-semibold text-sm sm:text-base text-ink-secondary">
            {dormantCount} {dormantCount === 1 ? 'account' : 'accounts'} with no activity in 90+ days
          </summary>
          <div className="mt-2 space-y-1">
            {nw.dormant_accounts.map((account) => (
              <p key={account.account_key} className="text-sm text-ink-secondary">
                {account.account_name} — no activity in {account.days_inactive} days ·{' '}
                {formatCurrency(account.balance)}
              </p>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
