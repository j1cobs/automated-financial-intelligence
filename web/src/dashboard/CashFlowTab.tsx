import { useState } from 'react';
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
import type { TooltipContentProps, MouseHandlerDataParam } from 'recharts';
import { useCashFlow } from '../lib/queries';
import { MetricInfoBadge } from './MetricTile';
import { TabSkeleton, ErrorState } from './LoadingState';
import { PeriodTransactionsPreview } from './PeriodTransactionsPreview';
import { daysBefore, parseWeekRange, parseMonthRange } from '../lib/dateRanges';
import { formatCategory } from '../lib/categories';
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
  onFillTextColor,
  sequentialColor,
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
} from './chartTheme';

/** "Other" bucket for the categorical tail — see `pivotCategoryHeatmap`. */
const OTHER_LABEL = 'Other';

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

/** Resolves a `YYYY-MM` month key to its date range plus a human label
 *  ("August 2026", matching `FilterOptions.months`'s format elsewhere in the
 *  UI). Shared by every chart that opens `PeriodTransactionsPreview` for a
 *  clicked month -- the monthly bar chart, the owner chart, and the category
 *  heatmap. Returns `null` for an unparseable month key, meaning "no
 *  drill-down available" rather than opening a preview with an error. */
function resolveMonthPeriod(month: string): { dateFrom: string; dateTo: string; monthLabel: string } | null {
  const range = parseMonthRange(month);
  if (!range) return null;
  const monthLabel = new Date(`${range.from}T00:00:00`).toLocaleDateString('en-US', {
    month: 'long',
    year: 'numeric',
  });
  return { dateFrom: range.from, dateTo: range.to, monthLabel };
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

/** Row cap for the category heatmap. Higher than `CATEGORICAL_SLOTS` (8):
 *  that limit exists to keep a *legend* with distinct per-category hues
 *  readable, but the heatmap uses one sequential intensity scale instead of
 *  per-category colours, so there's no legend-crowding reason to fold this
 *  early -- more rows means more signal for spotting which category spiked. */
const HEATMAP_ROW_CAP = 18;

interface CategoryHeatmapRow {
  category: string;
  total: number;
  cells: Record<string, number>;
}

/**
 * Pivots `category_distribution` (one row per `{month, category}`) into
 * category-major rows for the heatmap: one row per category (sorted by total
 * spend descending), one cell per month. Categories past `HEATMAP_ROW_CAP`
 * (by total spend across the whole window) are folded into an `"Other"` row.
 */
function pivotCategoryHeatmap(items: CategoryDistributionItem[]): {
  rows: CategoryHeatmapRow[];
  months: string[];
  maxAmount: number;
} {
  const totals = new Map<string, number>();
  const monthSet = new Set<string>();
  for (const item of items) {
    totals.set(item.category, (totals.get(item.category) ?? 0) + item.amount);
    monthSet.add(item.month);
  }
  const bySpendDesc = Array.from(totals.keys()).sort((a, b) => (totals.get(b) ?? 0) - (totals.get(a) ?? 0));
  const folded = bySpendDesc.length > HEATMAP_ROW_CAP;
  const kept = new Set(folded ? bySpendDesc.slice(0, HEATMAP_ROW_CAP - 1) : bySpendDesc);
  const orderedCategories = folded
    ? [...bySpendDesc.slice(0, HEATMAP_ROW_CAP - 1), OTHER_LABEL]
    : bySpendDesc;

  const cellsByCategory = new Map<string, Record<string, number>>();
  const rowTotals = new Map<string, number>();
  orderedCategories.forEach((category) => cellsByCategory.set(category, {}));

  for (const item of items) {
    const key = kept.has(item.category) ? item.category : OTHER_LABEL;
    const cells = cellsByCategory.get(key)!;
    cells[item.month] = (cells[item.month] ?? 0) + item.amount;
    rowTotals.set(key, (rowTotals.get(key) ?? 0) + item.amount);
  }

  const rows: CategoryHeatmapRow[] = orderedCategories.map((category) => ({
    category,
    total: rowTotals.get(category) ?? 0,
    cells: cellsByCategory.get(category) ?? {},
  }));
  const maxAmount = rows.reduce((max, row) => Math.max(max, ...Object.values(row.cells), 0), 0);

  return { rows, months: Array.from(monthSet).sort(), maxAmount };
}

/**
 * Category x month heatmap. Cell fill uses the shared sequential intensity
 * scale (`sequentialColor`, `chartTheme.ts`) rather than per-category hues --
 * the `dataviz` skill requires a scale like this to never rely on colour
 * alone, so every cell also shows its exact amount as text. Cells fold into
 * an `"Other"` row past `HEATMAP_ROW_CAP` and that row is never clickable,
 * mirroring the categorical charts elsewhere on this tab.
 */
function CategoryHeatmap({
  rows,
  months,
  maxAmount,
  onCellClick,
}: {
  rows: CategoryHeatmapRow[];
  months: string[];
  maxAmount: number;
  onCellClick: (category: string, month: string) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-max border-collapse text-xs sm:text-sm">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 bg-surface-1 p-1 text-left font-medium text-ink-secondary sm:p-2">
              Category
            </th>
            {months.map((month) => (
              <th key={month} className="p-1 text-right font-medium text-ink-secondary sm:p-2">
                {month}
              </th>
            ))}
            <th className="p-1 text-right font-medium text-ink-secondary sm:p-2">Total</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.category}>
              <th
                scope="row"
                className="sticky left-0 z-10 whitespace-nowrap bg-surface-1 p-1 text-left font-normal text-ink sm:p-2"
              >
                {formatCategory(row.category)}
              </th>
              {months.map((month) => {
                const amount = row.cells[month] ?? 0;
                const fill =
                  amount > 0 ? sequentialColor(maxAmount > 0 ? amount / maxAmount : 0) : 'transparent';
                const clickable = amount > 0 && row.category !== OTHER_LABEL;
                return (
                  <td
                    key={month}
                    className="p-1 text-right tabular-nums sm:p-2"
                    style={{ backgroundColor: fill, cursor: clickable ? 'pointer' : 'default' }}
                    onClick={clickable ? () => onCellClick(row.category, month) : undefined}
                    title={`${formatCategory(row.category)} · ${month}: ${money(amount)}`}
                  >
                    {amount > 0 && <span style={{ color: onFillTextColor(fill) }}>{shortMoney(amount)}</span>}
                  </td>
                );
              })}
              <td className="p-1 text-right font-medium tabular-nums text-ink sm:p-2">
                {shortMoney(row.total)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
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
  metricKey,
}: {
  label: string;
  value: number;
  format: 'currency' | 'percent' | 'number';
  tone: Tone;
  /** For `pos-neg`, the value whose sign decides the colour (usually `value` itself). */
  sign?: number;
  /** Optional metricInfo key (Fix 13) -- renders the hover/tap tooltip badge. */
  metricKey?: string;
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
      <div className="flex items-start justify-between gap-1">
        <p className="text-xs sm:text-sm font-medium text-ink-secondary">{label}</p>
        {metricKey && <MetricInfoBadge metricKey={metricKey} />}
      </div>
      <p className={`mt-1 sm:mt-2 text-lg sm:text-2xl font-bold tabular-nums ${valueClass}`}>{formatted}</p>
    </div>
  );
}

/** Income vs. expenses over a period, grouped bars plus a net line. Shared by the
 *  monthly and weekly charts (Fix 6 / Fix 10) -- same shape, same treatment.
 *  Both call sites pass `onBarClick` so a click on either chart opens the
 *  same (period-agnostic) `PeriodTransactionsPreview` -- mirrors how the
 *  category-breakdown chart below already sets `cursor`/`onClick` per-bar. */
function FlowBarChart<T extends CashFlowSeriesItem | WeeklyTrendItem>({
  title,
  data,
  xKey,
  themeEpoch,
  onBarClick,
}: {
  title: string;
  data: T[];
  xKey: 'month' | 'week';
  themeEpoch: number;
  onBarClick?: (row: T) => void;
}) {
  const income = incomeColor();
  const expense = expenseColor();
  const handleClick = onBarClick
    ? (bar: { payload?: T }) => {
        if (bar.payload) onBarClick(bar.payload);
      }
    : undefined;
  return (
    <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
      <h3 className="mb-4 text-base sm:text-lg font-semibold text-ink">{title}</h3>
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
              cursor={onBarClick ? 'pointer' : undefined}
              onClick={handleClick}
              {...surfaceGapProps()}
            />
            <Bar
              dataKey="expenses"
              name="Expenses"
              fill={expense}
              maxBarSize={BAR_MAX_SIZE}
              radius={BAR_RADIUS}
              cursor={onBarClick ? 'pointer' : undefined}
              onClick={handleClick}
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
export function CashFlowTab({
  onDrillDownToTransactions,
}: {
  /** Rolling-30-day-spend point click -> switch to Transactions filtered to
   *  that 30-day window (Dashboard.tsx owns the snapshot + tab switch; this
   *  tab just reports which range was clicked). Optional so this component
   *  keeps working standalone (e.g. in tests) with no drill-down wired up. */
  onDrillDownToTransactions?: (dateFrom: string, dateTo: string) => void;
}) {
  const { data, isLoading, error, refetch } = useCashFlow();
  const themeEpoch = useChartTheme();
  const [previewPeriod, setPreviewPeriod] = useState<{
    label: string;
    dateFrom: string;
    dateTo: string;
    owner?: string;
    category?: string;
  } | null>(null);

  // Weekly/monthly bar click -> open PeriodTransactionsPreview for the
  // clicked bar's exact date range. `parseWeekRange`/`parseMonthRange`
  // return `null` for an unparseable value, which both are documented to
  // mean "no drill-down available" -- so an unparseable bar simply doesn't
  // open a preview, rather than opening one with an error message.
  function handleWeekBarClick(row: WeeklyTrendItem) {
    const range = parseWeekRange(row.week);
    if (!range) return;
    setPreviewPeriod({
      label: `Week of ${range.from} – ${range.to}`,
      dateFrom: range.from,
      dateTo: range.to,
    });
  }

  function handleMonthBarClick(row: CashFlowSeriesItem) {
    const period = resolveMonthPeriod(row.month);
    if (!period) return;
    setPreviewPeriod({ label: period.monthLabel, dateFrom: period.dateFrom, dateTo: period.dateTo });
  }

  // "Monthly net cash flow by holder" bar click -> open the preview filtered
  // to both the clicked month AND the clicked owner's segment, since that's
  // the whole point of breaking this chart down by holder in the first place.
  function handleOwnerBarClick(month: string, owner: string) {
    const period = resolveMonthPeriod(month);
    if (!period) return;
    setPreviewPeriod({
      label: `${owner} – ${period.monthLabel}`,
      dateFrom: period.dateFrom,
      dateTo: period.dateTo,
      owner,
    });
  }

  // Category heatmap cell click -> open the preview filtered to that
  // category + month. `OTHER_LABEL` is a synthetic aggregate, never clickable
  // (mirrors the old stacked-bar chart's rule).
  function handleCategoryCellClick(category: string, month: string) {
    if (category === OTHER_LABEL) return;
    const period = resolveMonthPeriod(month);
    if (!period) return;
    setPreviewPeriod({
      label: `${formatCategory(category)} – ${period.monthLabel}`,
      dateFrom: period.dateFrom,
      dateTo: period.dateTo,
      category,
    });
  }

  // Rolling-30-day-spend point click. Each point's `date` is the *last* day
  // of the 30-day window it summarizes (see the chart's own tooltip copy
  // below), so the window is [date - 29 days, date].
  function handleRollingSpendClick(row: RollingSpendItem) {
    if (!onDrillDownToTransactions) return;
    const from = daysBefore(row.date, 29);
    if (!from) return;
    onDrillDownToTransactions(from, row.date);
  }

  if (isLoading) {
    return <TabSkeleton />;
  }

  if (error) {
    return (
      <div className="space-y-4">
        <h2 className="text-base sm:text-lg font-semibold text-ink">Cash Flow</h2>
        <ErrorState
          message="Failed to load cash flow data. Please try again later."
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-4">
        <h2 className="text-base sm:text-lg font-semibold text-ink">Cash Flow</h2>
        <div className="rounded-lg border border-hairline bg-surface-2 p-4">
          <p className="text-sm text-ink-secondary">No cash flow data available.</p>
        </div>
      </div>
    );
  }

  const { rows: ownerRows, owners } = pivotByOwner(data.monthly_net_by_owner);
  const {
    rows: heatmapRows,
    months: heatmapMonths,
    maxAmount: heatmapMaxAmount,
  } = pivotCategoryHeatmap(data.category_distribution);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base sm:text-lg font-semibold text-ink">Cash Flow</h2>
      </div>

      {/* Key metrics stat tiles */}
      <div className="grid grid-cols-2 gap-2 sm:gap-4 sm:grid-cols-3 lg:grid-cols-7">
        <StatTile
          label="Total Income"
          value={data.income}
          format="currency"
          tone="income"
          metricKey="income"
        />
        <StatTile
          label="Total Expenses"
          value={data.expenses}
          format="currency"
          tone="expense"
          metricKey="expenses"
        />
        <StatTile
          label="Net Flow"
          value={data.net_flow}
          format="currency"
          tone="pos-neg"
          metricKey="net_flow"
        />
        <StatTile
          label="Savings Rate"
          value={data.savings_rate}
          format="percent"
          tone="pos-neg"
          sign={data.net_flow}
          metricKey="savings_rate"
        />
        <StatTile
          label="Reimbursed"
          value={data.reimbursed}
          format="currency"
          tone="neutral"
          metricKey="reimbursed"
        />
        <StatTile
          label="Transfers"
          value={data.transfer_count}
          format="number"
          tone="neutral"
          metricKey="transfer_count"
        />
        <StatTile
          label="Flagged"
          value={data.flagged_count}
          format="number"
          tone="warn"
          metricKey="flagged_count"
        />
      </div>
      <p className="text-xs text-ink-muted">
        Inter-account transfers are excluded from income and expense totals.
      </p>

      {/* Income vs Expenses Chart -- clicking a bar opens a two-column preview
          of that month's transactions (income vs expenses). */}
      {data.month_over_month.length > 0 && (
        <FlowBarChart
          title="Income vs Expenses"
          data={data.month_over_month}
          xKey="month"
          themeEpoch={themeEpoch}
          onBarClick={handleMonthBarClick}
        />
      )}

      {/* Income vs Expenses by week -- clicking a bar opens a two-column preview
          of that week's transactions (income vs expenses). */}
      {data.weekly_trend.length > 0 && (
        <FlowBarChart
          title="Income vs Expenses (weekly)"
          data={data.weekly_trend}
          xKey="week"
          themeEpoch={themeEpoch}
          onBarClick={handleWeekBarClick}
        />
      )}

      {/* Rolling 30-day spend Chart -- deliberately single-axis; see RollingSpendTooltip. */}
      {data.rolling_30d_spend.length > 0 && (
        <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
          <h3 className="mb-1 text-base sm:text-lg font-semibold text-ink">Rolling 30-day spend</h3>
          <p className="mb-4 text-xs text-ink-muted">
            total spent in the 30 days ending on each date — hover for the daily average
          </p>
          <div
            className="h-48 sm:h-64 w-full"
            data-testid="rolling-spend-chart"
            style={onDrillDownToTransactions ? { cursor: 'pointer' } : undefined}
          >
            <ResponsiveContainer key={themeEpoch} width="100%" height="100%">
              <LineChart
                data={data.rolling_30d_spend}
                margin={{ ...CHART_MARGIN.default }}
                onClick={
                  onDrillDownToTransactions
                    ? (state: MouseHandlerDataParam) => {
                        const label = state?.activeLabel;
                        if (typeof label !== 'string') return;
                        const row = data.rolling_30d_spend.find((item) => item.date === label);
                        if (row) handleRollingSpendClick(row);
                      }
                    : undefined
                }
              >
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
                  activeDot={activeDotProps()}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Monthly net cash flow by holder */}
      {ownerRows.length > 0 && (
        <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
          <h3 className="mb-4 text-base sm:text-lg font-semibold text-ink">
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
                      cursor="pointer"
                      onClick={(bar: { payload?: Record<string, number | string> }) => {
                        const month = bar.payload?.month;
                        if (typeof month === 'string') handleOwnerBarClick(month, owner);
                      }}
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
      {heatmapRows.length > 0 && (
        <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
          <h3 className="mb-1 text-base sm:text-lg font-semibold text-ink">
            Monthly expense breakdown by category
          </h3>
          <p className="mb-4 text-xs text-ink-muted">
            Darker cells mean more spent that month. Click a cell to see those transactions.
          </p>
          <CategoryHeatmap
            rows={heatmapRows}
            months={heatmapMonths}
            maxAmount={heatmapMaxAmount}
            onCellClick={handleCategoryCellClick}
          />
        </div>
      )}

      {previewPeriod && (
        <PeriodTransactionsPreview
          label={previewPeriod.label}
          dateFrom={previewPeriod.dateFrom}
          dateTo={previewPeriod.dateTo}
          owner={previewPeriod.owner}
          category={previewPeriod.category}
          onClose={() => setPreviewPeriod(null)}
        />
      )}
    </div>
  );
}
