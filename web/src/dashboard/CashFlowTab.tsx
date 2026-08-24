import {
  ComposedChart,
  BarChart,
  Bar,
  Line,
  LineChart,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import type { TooltipContentProps } from 'recharts';
import { useCashFlow } from '../lib/queries';
import type {
  RollingSpendItem,
  CashFlowSeriesItem,
  WeeklyTrendItem,
  MonthlyNetByOwnerItem,
  CategoryDistributionItem,
} from '../lib/types';
import {
  useChartTheme,
  categoricalColor,
  incomeColor,
  expenseColor,
  positiveColor,
  neutralColor,
  onFillTextColor,
  gridProps,
  xAxisProps,
  yAxisProps,
  tooltipProps,
  legendProps,
  referenceLineProps,
  surfaceGapProps,
  CHART_MARGIN,
  BAR_MAX_SIZE,
  BAR_RADIUS,
  LINE_PROPS,
  activeDotProps,
  CATEGORICAL_SLOTS,
} from './chartTheme';

/** "Other" bucket for the categorical tail — see `pivotCategoryDistribution`. */
const OTHER_LABEL = 'Other';

/** Square corners for a stacked segment that isn't the topmost one -- only the
 *  last-drawn (topmost) segment gets `BAR_RADIUS`'s rounded data-end. */
const STACK_SEGMENT_RADIUS: [number, number, number, number] = [0, 0, 0, 0];

/** Categorical slots 3-5 (index 2-4: aqua, yellow, magenta) fall below 3:1 on the
 *  light surface. The `dataviz` skill's relief for that is a visible direct label,
 *  not a colour swap, so any series landing on one of those slots gets a label. */
function needsDirectLabelRelief(index: number): boolean {
  return index === 2 || index === 3 || index === 4;
}

function money(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function shortMoney(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value);
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

/** Direct-label props for a `<Bar>` landing on a low-contrast categorical slot.
 *  `undefined` for every other slot -- the skill calls direct labels "selective",
 *  not "every point". */
function directLabelProps(index: number, fill: string) {
  if (!needsDirectLabelRelief(index)) return undefined;
  return {
    position: 'insideTop' as const,
    fill: onFillTextColor(fill),
    fontSize: 10,
    formatter: (value: string | number | boolean | null | undefined) =>
      typeof value === 'number' && value ? shortMoney(value) : '',
  };
}

/**
 * `data.rolling_30d_spend` tooltip. Shows the 30-day total and the per-day figure
 * it implies -- the per-day number is why this tooltip exists: the series used to
 * be labelled "Daily Spend" while plotting a 30-day total, so a ~$7,500 month read
 * as a $7,500 day.
 */
function RollingSpendTooltip({ active, payload, label }: Partial<TooltipContentProps<number, string>>) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }
  const row = payload[0]?.payload as RollingSpendItem | undefined;
  if (!row) {
    return null;
  }
  const props = tooltipProps();
  return (
    <div style={props.contentStyle} className="text-xs sm:text-sm">
      <p style={props.labelStyle}>{String(label)}</p>
      <p style={props.itemStyle}>{money(row.amount)} over the previous 30 days</p>
      <p className="text-ink-muted">{money(row.daily_avg)} per day on average</p>
    </div>
  );
}

/**
 * Pivots `monthly_net_by_owner` (one row per `{month, owner}`) into wide rows
 * keyed by owner, so Recharts can drive one `<Bar>` per owner off a stable set
 * of columns instead of a client-side reshape happening more than once.
 */
function pivotByOwner(items: MonthlyNetByOwnerItem[]): {
  rows: Record<string, number | string>[];
  owners: string[];
} {
  const owners = Array.from(new Set(items.map((item) => item.owner))).sort();
  const byMonth = new Map<string, Record<string, number | string>>();
  for (const item of items) {
    let row = byMonth.get(item.month);
    if (!row) {
      row = { month: item.month };
      owners.forEach((owner) => (row![owner] = 0));
      byMonth.set(item.month, row);
    }
    row[item.owner] = item.amount;
  }
  const rows = Array.from(byMonth.values()).sort((a, b) => String(a.month).localeCompare(String(b.month)));
  return { rows, owners };
}

/**
 * Pivots `category_distribution` (one row per `{month, category}`) into wide
 * rows keyed by category, for a stacked bar. The categorical palette has
 * exactly `CATEGORICAL_SLOTS` (8) slots, but the category list is unbounded, so
 * once there are more than 8 distinct categories the smallest ones (by total
 * spend across the whole window) are folded into an `"Other"` bucket rather
 * than cycling the palette onto a 9th hue.
 */
function pivotCategoryDistribution(items: CategoryDistributionItem[]): {
  rows: Record<string, number | string>[];
  categories: string[];
} {
  const totals = new Map<string, number>();
  for (const item of items) {
    totals.set(item.category, (totals.get(item.category) ?? 0) + item.amount);
  }
  const bySpendDesc = Array.from(totals.keys()).sort((a, b) => (totals.get(b) ?? 0) - (totals.get(a) ?? 0));
  const folded = bySpendDesc.length > CATEGORICAL_SLOTS;
  const kept = new Set(folded ? bySpendDesc.slice(0, CATEGORICAL_SLOTS - 1) : bySpendDesc);
  const categories = folded ? [...bySpendDesc.slice(0, CATEGORICAL_SLOTS - 1), OTHER_LABEL] : bySpendDesc;

  const byMonth = new Map<string, Record<string, number | string>>();
  for (const item of items) {
    const key = kept.has(item.category) ? item.category : OTHER_LABEL;
    let row = byMonth.get(item.month);
    if (!row) {
      row = { month: item.month };
      categories.forEach((category) => (row![category] = 0));
      byMonth.set(item.month, row);
    }
    row[key] = (Number(row[key]) || 0) + item.amount;
  }
  const rows = Array.from(byMonth.values()).sort((a, b) => String(a.month).localeCompare(String(b.month)));
  return { rows, categories };
}

type Tone = 'income' | 'expense' | 'pos-neg' | 'warn' | 'neutral';

/**
 * KPI tile. Income/expenses are identity, not polarity (the `dataviz` skill's
 * note on `incomeColor`/`expenseColor` in `chartTheme.ts` applies to the tiles
 * too, not just the chart series) so they wear the flow hues rather than
 * green/red. Net flow and savings rate ARE polarity -- up is genuinely better
 * than down -- so those get the semantic pos/neg tokens. Flagged is a warning
 * state; transfers is a plain count.
 */
function StatTile({
  label,
  value,
  format,
  tone,
  sign,
}: {
  label: string;
  value: number;
  format: 'currency' | 'percent' | 'number';
  tone: Tone;
  /** For `pos-neg`, the value whose sign decides the colour (usually `value` itself). */
  sign?: number;
}) {
  const formatted =
    format === 'currency'
      ? money(value)
      : format === 'percent'
        ? formatPercent(value)
        : value.toLocaleString();

  let valueClass = 'text-ink';
  if (tone === 'income') valueClass = 'text-flow-income';
  else if (tone === 'expense') valueClass = 'text-flow-expense';
  else if (tone === 'warn') valueClass = 'text-warn-text';
  else if (tone === 'neutral') valueClass = 'text-ink-secondary';
  else if (tone === 'pos-neg') valueClass = (sign ?? value) >= 0 ? 'text-pos-text' : 'text-neg-text';

  return (
    <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
      <p className="text-xs sm:text-sm font-medium text-ink-secondary">{label}</p>
      <p className={`mt-1 sm:mt-2 text-lg sm:text-2xl font-bold tabular-nums ${valueClass}`}>{formatted}</p>
    </div>
  );
}

/** Income vs. expenses over a period, grouped bars plus a net line. Shared by the
 *  monthly and weekly charts (Fix 6 / Fix 10) -- same shape, same treatment. */
function FlowBarChart({
  title,
  data,
  xKey,
  themeEpoch,
}: {
  title: string;
  data: (CashFlowSeriesItem | WeeklyTrendItem)[];
  xKey: 'month' | 'week';
  themeEpoch: number;
}) {
  const income = incomeColor();
  const expense = expenseColor();
  return (
    <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
      <h3 className="mb-4 text-sm sm:text-base font-semibold text-ink">{title}</h3>
      <div className="h-56 sm:h-80 w-full">
        <ResponsiveContainer key={themeEpoch} width="100%" height="100%">
          <ComposedChart data={data} margin={{ ...CHART_MARGIN.default }}>
            <CartesianGrid {...gridProps()} />
            <XAxis dataKey={xKey} {...xAxisProps()} />
            <YAxis {...yAxisProps()} tickFormatter={(value) => shortMoney(Number(value))} />
            <Tooltip {...tooltipProps()} formatter={(value) => money(Number(value))} />
            <Legend {...legendProps()} />
            <Bar
              dataKey="income"
              name="Income"
              fill={income}
              maxBarSize={BAR_MAX_SIZE}
              radius={BAR_RADIUS}
              {...surfaceGapProps()}
            />
            <Bar
              dataKey="expenses"
              name="Expenses"
              fill={expense}
              maxBarSize={BAR_MAX_SIZE}
              radius={BAR_RADIUS}
              {...surfaceGapProps()}
            />
            <Line
              {...LINE_PROPS}
              dataKey="net"
              name="Net"
              stroke={positiveColor()}
              activeDot={activeDotProps()}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/**
 * Cash Flow tab — monthly/weekly trends, rolling spend, net by holder, category
 * distribution. Uses `useCashFlow()` from `lib/queries.ts` (returns
 * `CashFlowResponse` from `lib/types.ts`) and Recharts.
 */
export function CashFlowTab() {
  const { data, isLoading, error } = useCashFlow();
  const themeEpoch = useChartTheme();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-ink">Cash Flow</h2>
        <div className="flex items-center justify-center rounded-lg bg-surface-2 py-12">
          <p className="text-sm text-ink-secondary">Loading cash flow data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-ink">Cash Flow</h2>
        <div className="rounded-lg border border-hairline bg-surface-2 p-4">
          <p className="text-sm text-neg-text">Failed to load cash flow data. Please try again later.</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-ink">Cash Flow</h2>
        <div className="rounded-lg border border-hairline bg-surface-2 p-4">
          <p className="text-sm text-ink-secondary">No cash flow data available.</p>
        </div>
      </div>
    );
  }

  const { rows: ownerRows, owners } = pivotByOwner(data.monthly_net_by_owner);
  const { rows: categoryRows, categories } = pivotCategoryDistribution(data.category_distribution);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-ink">Cash Flow</h2>
      </div>

      {/* Key metrics stat tiles */}
      <div className="grid grid-cols-2 gap-2 sm:gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <StatTile label="Total Income" value={data.income} format="currency" tone="income" />
        <StatTile label="Total Expenses" value={data.expenses} format="currency" tone="expense" />
        <StatTile label="Net Flow" value={data.net_flow} format="currency" tone="pos-neg" />
        <StatTile
          label="Savings Rate"
          value={data.savings_rate}
          format="percent"
          tone="pos-neg"
          sign={data.net_flow}
        />
        <StatTile label="Transfers" value={data.transfer_count} format="number" tone="neutral" />
        <StatTile label="Flagged" value={data.flagged_count} format="number" tone="warn" />
      </div>
      <p className="text-xs text-ink-muted">
        Inter-account transfers are excluded from income and expense totals.
      </p>

      {/* Income vs Expenses Chart */}
      {data.month_over_month.length > 0 && (
        <FlowBarChart
          title="Income vs Expenses"
          data={data.month_over_month}
          xKey="month"
          themeEpoch={themeEpoch}
        />
      )}

      {/* Income vs Expenses by week */}
      {data.weekly_trend.length > 0 && (
        <FlowBarChart
          title="Income vs Expenses (weekly)"
          data={data.weekly_trend}
          xKey="week"
          themeEpoch={themeEpoch}
        />
      )}

      {/* Rolling 30-day spend Chart -- deliberately single-axis; see RollingSpendTooltip. */}
      {data.rolling_30d_spend.length > 0 && (
        <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
          <h3 className="mb-1 text-sm sm:text-base font-semibold text-ink">Rolling 30-day spend</h3>
          <p className="mb-4 text-xs text-ink-muted">
            total spent in the 30 days ending on each date — hover for the daily average
          </p>
          <div className="h-48 sm:h-64 w-full" data-testid="rolling-spend-chart">
            <ResponsiveContainer key={themeEpoch} width="100%" height="100%">
              <LineChart data={data.rolling_30d_spend} margin={{ ...CHART_MARGIN.default }}>
                <CartesianGrid {...gridProps()} />
                <XAxis dataKey="date" {...xAxisProps()} />
                {/* Deliberately ONE y-axis. `daily_avg` is `amount / 30`, so plotting it
                    as a second series draws the identical curve at 1/30 scale against a
                    second scale — no added information, and a dual axis implies a
                    relationship between two quantities that are the same quantity. The
                    per-day figure lives in the tooltip instead. */}
                <YAxis {...yAxisProps()} tickFormatter={(value) => shortMoney(Number(value))} />
                <Tooltip content={<RollingSpendTooltip />} cursor={tooltipProps().cursor} />
                <Line
                  type="monotone"
                  dataKey="amount"
                  name="30-day total"
                  stroke={expenseColor()}
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Monthly net cash flow by holder */}
      {ownerRows.length > 0 && (
        <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
          <h3 className="mb-4 text-sm sm:text-base font-semibold text-ink">
            Monthly net cash flow by holder
          </h3>
          <div className="h-56 sm:h-80 w-full">
            <ResponsiveContainer key={themeEpoch} width="100%" height="100%">
              <BarChart data={ownerRows} margin={{ ...CHART_MARGIN.default }}>
                <CartesianGrid {...gridProps()} />
                <XAxis dataKey="month" {...xAxisProps()} />
                <YAxis {...yAxisProps()} tickFormatter={(value) => shortMoney(Number(value))} />
                <Tooltip {...tooltipProps()} formatter={(value) => money(Number(value))} />
                <Legend {...legendProps()} />
                <ReferenceLine y={0} {...referenceLineProps()} />
                {owners.map((owner, index) => {
                  const fill = categoricalColor(index);
                  return (
                    <Bar
                      key={owner}
                      dataKey={owner}
                      name={owner}
                      fill={fill}
                      maxBarSize={BAR_MAX_SIZE}
                      radius={BAR_RADIUS}
                      label={directLabelProps(index, fill)}
                      {...surfaceGapProps()}
                    />
                  );
                })}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Monthly expense breakdown by category */}
      {categoryRows.length > 0 && (
        <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
          <h3 className="mb-4 text-sm sm:text-base font-semibold text-ink">
            Monthly expense breakdown by category
          </h3>
          <div className="h-56 sm:h-80 w-full">
            <ResponsiveContainer key={themeEpoch} width="100%" height="100%">
              <BarChart data={categoryRows} margin={{ ...CHART_MARGIN.default }}>
                <CartesianGrid {...gridProps()} />
                <XAxis dataKey="month" {...xAxisProps()} />
                <YAxis {...yAxisProps()} tickFormatter={(value) => shortMoney(Number(value))} />
                <Tooltip {...tooltipProps()} formatter={(value) => money(Number(value))} />
                <Legend {...legendProps()} />
                {categories.map((category, index) => {
                  const fill = index < CATEGORICAL_SLOTS ? categoricalColor(index) : neutralColor();
                  return (
                    <Bar
                      key={category}
                      dataKey={category}
                      name={category}
                      stackId="expenses"
                      fill={fill}
                      maxBarSize={BAR_MAX_SIZE}
                      radius={index === categories.length - 1 ? BAR_RADIUS : STACK_SEGMENT_RADIUS}
                      label={directLabelProps(index, fill)}
                      {...surfaceGapProps()}
                    />
                  );
                })}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
