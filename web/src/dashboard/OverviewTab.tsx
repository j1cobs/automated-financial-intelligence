import { useState, type ReactNode } from 'react';
import { useOverview } from '../lib/queries';
import { useSetCreditLimit } from '../lib/mutations';
import { useFilters } from '../lib/FilterContext';
import type {
  AssetMixItem,
  CreditUtilizationItem,
  MonthOverMonthItem,
  OwnerBalanceItem,
  TopCategoryItem,
} from '../lib/types';
import { MetricTile, MetricInfoBadge } from './MetricTile';
import { TabSkeleton, ErrorState } from './LoadingState';
import { strings } from '../lib/strings';
import { formatCategory } from '../lib/categories';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  LabelList,
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
  onFillTextColor,
  AXIS_FONT_SIZE,
  CHART_MARGIN,
  BAR_MAX_SIZE,
  BAR_RADIUS_HORIZONTAL,
  truncateTickLabel,
} from './chartTheme';

/** Shared category-axis width (Item 2): wide enough for realistic account
 *  names ("World Elite Mastercard (....3265)") and category/description
 *  labels without eating most of the chart's plottable area. Paired with
 *  `truncateTickLabel`'s character budget in `chartTheme.ts`. */
const CATEGORY_AXIS_WIDTH = 160;

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

/** Pivots the API's long `{balance, subtype_label}` rows into one wide row so
 *  a single stacked `<Bar>` per subtype can plot the Asset Mix chart (Item E:
 *  a horizontal stacked bar in place of a pie, per the `dataviz` skill's
 *  part-to-whole guidance). `category` is a constant field, not real data --
 *  it exists only to give the hidden category axis a stable key. */
function buildAssetMixRow(items: AssetMixItem[]): Record<string, number | string> {
  const row: Record<string, number | string> = { category: 'Assets' };
  for (const item of items) {
    row[item.subtype_label] = item.balance;
  }
  return row;
}

const ASSET_MIX_HEIGHT = 120;

interface AssetMixLabelProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
}

/** Direct value+percent label centered on a stacked segment -- omitted (falls
 *  back to the legend + tooltip) when the segment is too narrow to hold text
 *  without overlapping its neighbours. 56px is roughly enough for a short
 *  label like "Savings 12%" at the shared axis font size. */
function renderAssetMixSegmentLabel(props: AssetMixLabelProps, label: string, pct: number, fill: string) {
  const { x, y, width, height } = props;
  if (x == null || y == null || width == null || height == null || width < 56) {
    return null;
  }
  return (
    <text
      x={x + width / 2}
      y={y + height / 2}
      textAnchor="middle"
      dominantBaseline="central"
      fontSize={AXIS_FONT_SIZE}
      fontWeight={600}
      fill={onFillTextColor(fill)}
    >
      {`${label} ${(pct * 100).toFixed(0)}%`}
    </text>
  );
}

/** Fixed order matches the stacked-series colors the old single Owner
 *  Balances chart used (`categoricalColor(0)` depository, `(1)` investment,
 *  `(7)` credit, `(6)` other) -- Item F keeps the same colors, just moves
 *  them onto per-account bars instead of stacked segments. */
const ACCOUNT_TYPE_COLOR_INDEX: Record<string, number> = {
  depository: 0,
  investment: 1,
  credit: 7,
  other: 6,
};

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  depository: 'Depository',
  investment: 'Investment',
  credit: 'Credit',
  other: 'Other',
};

function accountTypeColor(type: string): string {
  const index = ACCOUNT_TYPE_COLOR_INDEX[type];
  return index != null ? categoricalColor(index) : categoricalColor(6);
}

/** Shared label-column width for `LabeledBarRow` -- fixed, not content-sized,
 *  so every row's bar starts at the same x position regardless of label
 *  length. Also what makes Owner Balances and Income Sources read as the
 *  same size: both are built from this one row shape. */
const LIST_LABEL_WIDTH_CLASS = 'w-36 sm:w-44';

/**
 * Item 4 (plus a later alignment fix): the shared "name + proportional bar +
 * value" row backing both Owner Balances and Income Sources. Originally each
 * had its own markup with a content-sized label (`shrink-0 whitespace-nowrap`),
 * which let a long label push that row's bar further right than its
 * neighbours' -- bars never lined up. `LIST_LABEL_WIDTH_CLASS` fixes the
 * label column's width instead, so every bar in a list starts at the same
 * point; `truncate` is a safety net for anything still too long for that
 * width (short_name/description are usually short enough not to need it).
 * `title={fullLabel}` is a plain HTML tooltip revealing the full,
 * untruncated name on hover -- Owner Balances had this already, Income
 * Sources now gets the identical behavior via this shared component.
 */
function LabeledBarRow({
  label,
  fullLabel,
  value,
  pct,
  color,
}: {
  label: string;
  fullLabel: string;
  value: number;
  pct: number;
  color: string;
}) {
  return (
    <div title={fullLabel} className="flex items-center gap-3 text-sm">
      <span className={`shrink-0 truncate text-ink-secondary ${LIST_LABEL_WIDTH_CLASS}`}>{label}</span>
      <span className="flex flex-1 items-center gap-2">
        <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-3">
          <span
            className="block h-full rounded-full"
            style={{ width: `${pct * 100}%`, backgroundColor: color }}
          />
        </span>
        <span className="shrink-0 tabular-nums text-ink">{formatCurrency(value)}</span>
      </span>
    </div>
  );
}

/**
 * Item 4: plain-HTML per-owner account list, replacing the Recharts small-
 * multiples bar chart entirely for this one component. A Recharts SVG
 * category-axis tick has a hard pixel budget that tuning width/truncation
 * further can't fix for real account names (confirmed insufficient by the
 * user in a prior round) -- `short_name` (server-computed in
 * `api/viewmodels.py::build_net_worth`, already short and mask-disambiguated
 * only when an owner actually has a collision) sits as plain text instead, so
 * there is no clipping to fight. Color still comes from the same
 * `accountTypeColor()` the swatch legend above this section uses, so that
 * legend stays accurate. `maxBalance` is the largest single account balance
 * across ALL owners in the response (not just this owner) -- passed in from
 * the parent -- so bar lengths stay comparable across the whole Owner
 * Balances section, not just within one owner's list.
 */
function OwnerBalanceMiniList({ owner, maxBalance }: { owner: OwnerBalanceItem; maxBalance: number }) {
  return (
    <div>
      <p className="mb-1 text-sm font-medium text-ink">{owner.owner}</p>
      <div className="space-y-1.5">
        {owner.accounts.map((account, index) => {
          const magnitude = Math.abs(account.value);
          const pct = maxBalance > 0 ? Math.min(1, magnitude / maxBalance) : 0;
          return (
            <LabeledBarRow
              key={`${account.account_name}-${index}`}
              label={account.short_name}
              fullLabel={account.account_name}
              value={account.value}
              pct={pct}
              color={accountTypeColor(account.type)}
            />
          );
        })}
      </div>
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
  className,
  contentClassName,
  children,
}: {
  title: string;
  caption?: string;
  /** Optional metricInfo key -- renders the Fix 13 tooltip badge beside the title. */
  metricKey?: string;
  /** Extra classes on the card's own wrapper, e.g. a shared `min-h-*` (Item 2). */
  className?: string;
  /** Extra classes on the content wrapper below the title/caption, e.g. to
   *  vertically center short content within a taller card (Item 2). */
  contentClassName?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={`relative flex h-full flex-col rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4 ${className ?? ''}`}
    >
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
      <div className={`mt-4 ${contentClassName ?? ''}`}>{children}</div>
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

/** Standard "lower is better" credit-utilization guidance: under ~30% utilization
 *  is considered healthy by most scoring models, 30-60% is elevated but not urgent,
 *  and above 60% meaningfully impacts credit health/available headroom. */
function creditTone(pct: number): MeterTone {
  if (pct >= 0.6) return 'serious';
  if (pct >= 0.3) return 'warn';
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
  const { data, isLoading, error, refetch } = useOverview();
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
  const assetMixTotal = nw.asset_mix.reduce((sum, item) => sum + item.balance, 0);
  // Fixed order (depository, investment, credit, other), filtered to types
  // actually present -- drives the Owner Balances shared legend.
  const ownerBalanceAccountTypes = Object.keys(ACCOUNT_TYPE_COLOR_INDEX).filter((type) =>
    nw.owner_balances.some((owner) => owner.accounts.some((account) => account.type === type)),
  );
  // Item 4: bar-length scale shared across every owner's mini list, not just within
  // one owner -- otherwise a small owner's largest account would read as "full".
  const maxOwnerAccountBalance = Math.max(
    0,
    ...nw.owner_balances.flatMap((owner) => owner.accounts.map((account) => Math.abs(account.value))),
  );
  // Income Sources (below) is built from the same `LabeledBarRow` as Owner
  // Balances, sized against its own max so its bars fill the row width
  // proportionally the same way -- `sortedIncomeBreakdown` is already sorted
  // descending, so the first row is the max.
  const maxIncomeAmount = sortedIncomeBreakdown[0]?.amount ?? 0;

  return (
    <div className="space-y-6">
      {/* KPI Tiles -- MetricTile (Fix 12/13): value + baseline comparison +
          sparkline where the API provides it, plus a hover/tap tooltip for
          every metric from `metricInfo.ts`. */}
      <div className="grid grid-cols-1 items-start gap-4 sm:grid-cols-2 lg:grid-cols-4">
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

      {/* Income and Expenses Row -- all three tiles pass an equivalent `metric`
          prop today, so this row isn't actually stretch-broken; `items-start`
          is added anyway as defense-in-depth against a future tile that doesn't. */}
      <div className="grid grid-cols-1 items-start gap-4 sm:grid-cols-3">
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
        <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
          <h3 className="mb-4 text-base sm:text-lg font-semibold text-ink">Savings Rate Trend</h3>
          <ResponsiveContainer width="100%" height={250} minWidth="100%">
            <LineChart data={ov.savings_rate_trend} margin={CHART_MARGIN.default}>
              <CartesianGrid {...gridProps()} />
              {/* `interval="preserveStartEnd"` thins month ticks on a short
                  filter-bounded series so labels don't crowd into each other;
                  a wider y-axis (64 vs. the 56px default) gives the
                  percent-formatted ticks (e.g. "-100.0%") room too -- both
                  scoped to this chart rather than the shared axis defaults. */}
              <XAxis dataKey="month" {...xAxisProps()} interval="preserveStartEnd" />
              <YAxis
                {...yAxisProps(64)}
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

      {/* Emergency Fund and Asset Mix -- paired because both are short, fixed
          -height cards (a few text lines + meter; a single 120px stacked bar).
          Item 2: both card wrappers share an explicit `min-h-56` (224px) so
          neither reads as top-aligned-with-blank-space -- Asset Mix's realistic
          rendered height is ASSET_MIX_HEIGHT (120px chart) + ~28px title line +
          ~24px vertical padding (p-3/p-4) + ~24px legend row underneath the
          chart (`Legend` renders below via `verticalAlign="bottom"`, inside the
          same ResponsiveContainer height, so no extra allowance needed there)
          -- comfortably under 224px with margin for the mb-4 gap. Emergency
          Fund's own content (number + meter + caption) is shorter, so it is
          vertically centered within the same reserved height via `flex
          flex-col justify-center` on its content wrapper, rather than reading
          as merely top-aligned. Owner Balances and Income Sources (below,
          after Credit Utilization and the Top Categories/Month-over-Month
          row) are the tall/variable pair instead -- regrouped by actual
          content height, not by adding more `items-start` CSS to a mismatched
          pairing. */}
      <div className="grid grid-cols-1 items-stretch gap-4 sm:gap-6 lg:grid-cols-2">
        {ov.emergency_fund_months !== null && (
          <Card
            title="Emergency Fund"
            caption="Liquid savings ÷ average monthly expenses."
            metricKey="emergency_fund_months"
            className="min-h-56"
            contentClassName="flex flex-1 flex-col justify-center"
          >
            <p className="text-2xl font-bold text-ink">{ov.emergency_fund_months.toFixed(1)} months</p>
            <div className="mt-3">
              <Meter pct={ov.emergency_fund_months / 6} tone={emergencyFundTone(ov.emergency_fund_months)} />
            </div>
            <p className="mt-2 text-xs text-ink-muted">Goal: 6 months of expenses covered.</p>
          </Card>
        )}

        {/* Asset Mix -- a single 100%-width horizontal stacked bar, not a pie:
            the `dataviz` skill's `choosing-a-form.md` prefers a stacked bar for
            part-to-whole data. Same color assignment as before
            (`categoricalScale(n)[index]`), just a different mark. */}
        {nw?.asset_mix && nw.asset_mix.length > 0 && (
          <div className="min-h-56 rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
            <h3 className="mb-4 text-base sm:text-lg font-semibold text-ink">Asset Mix</h3>
            <ResponsiveContainer width="100%" height={ASSET_MIX_HEIGHT} minWidth="100%">
              <BarChart
                data={[buildAssetMixRow(nw.asset_mix)]}
                layout="vertical"
                margin={CHART_MARGIN.compact}
              >
                <XAxis type="number" hide domain={[0, assetMixTotal]} />
                <YAxis dataKey="category" type="category" hide />
                <Tooltip {...tooltipProps()} formatter={(value) => formatCurrency(value as number)} />
                <Legend {...legendProps()} verticalAlign="bottom" />
                {nw.asset_mix.map((item, index) => {
                  const fill = categoricalScale(nw.asset_mix.length)[index];
                  const pct = assetMixTotal > 0 ? item.balance / assetMixTotal : 0;
                  return (
                    <Bar
                      key={item.subtype_label}
                      dataKey={item.subtype_label}
                      stackId="assets"
                      fill={fill}
                      name={item.subtype_label}
                      {...surfaceGapProps()}
                    >
                      <LabelList
                        dataKey={item.subtype_label}
                        content={(props: object) =>
                          renderAssetMixSegmentLabel(
                            props as AssetMixLabelProps,
                            item.subtype_label,
                            pct,
                            fill,
                          )
                        }
                      />
                    </Bar>
                  );
                })}
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
      <div className="grid grid-cols-1 items-start gap-4 sm:gap-6 lg:grid-cols-2">
        {ov?.top_categories && ov.top_categories.length > 0 && (
          <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
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
                <YAxis
                  dataKey="category"
                  type="category"
                  {...yAxisProps(CATEGORY_AXIS_WIDTH)}
                  tickFormatter={(value: string) => truncateTickLabel(formatCategory(value))}
                />
                <Tooltip
                  {...tooltipProps()}
                  formatter={(value) => formatCurrency(value as number)}
                  labelFormatter={(label) => formatCategory(label as string)}
                />
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
          <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
            <h3 className="mb-4 text-base sm:text-lg font-semibold text-ink">Month-over-Month by Category</h3>
            <ResponsiveContainer
              width="100%"
              height={Math.max(250, monthOverMonthRows.length * 32)}
              minWidth="100%"
            >
              <BarChart data={monthOverMonthRows} layout="vertical" margin={CHART_MARGIN.default}>
                <CartesianGrid {...gridProps()} />
                <XAxis type="number" {...xAxisProps()} tickFormatter={(value) => formatCurrency(value)} />
                <YAxis
                  dataKey="category"
                  type="category"
                  {...yAxisProps(CATEGORY_AXIS_WIDTH)}
                  tickFormatter={(value: string) => truncateTickLabel(formatCategory(value))}
                />
                <Tooltip
                  {...tooltipProps()}
                  formatter={(value) => formatCurrency(value as number)}
                  labelFormatter={(label) => formatCategory(label as string)}
                />
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

      {/* Owner Balances and Income Sources -- paired because both are
          genuinely data-driven with no fixed ceiling (small multiples that
          grow with owner/account count; a list that grows with income-source
          count), so no pairing strategy makes them match at every data
          volume. Item 3: both cards instead share a fixed `max-h-[420px]
          overflow-y-auto` on their CONTENT area only -- the outer card box
          stays a constant height regardless of data volume, and whichever
          side has more content than fits gets its own internal scrollbar.
          420px comfortably shows several owners/accounts or income rows
          before scrolling is needed. See the Emergency Fund/Asset Mix grid
          above for the short/fixed-height pair this was split from. */}
      <div className="grid grid-cols-1 items-start gap-4 sm:gap-6 lg:grid-cols-2">
        {/* Owner Balances -- small multiples: one plain-HTML mini list per
            owner (Item 4 -- see `OwnerBalanceMiniList`), account short name on
            the left, one row per account with a direct value label so every
            balance is visible without hovering. Color stays a single
            dimension (account type via `categoricalScale`) per the `dataviz`
            skill's categorical-hue rule -- owner is disambiguated by spatial
            separation, not a second hue. One shared legend covers account
            type for the whole group instead of repeating per list. */}
        {nw?.owner_balances && nw.owner_balances.length > 0 && (
          <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
            <h3 className="mb-4 text-base sm:text-lg font-semibold text-ink">Owner Balances</h3>
            <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1">
              {ownerBalanceAccountTypes.map((type) => (
                <span key={type} className="flex items-center gap-1.5 text-xs text-ink-secondary">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: accountTypeColor(type) }}
                  />
                  {ACCOUNT_TYPE_LABELS[type] ?? type}
                </span>
              ))}
            </div>
            <div className="grid max-h-[420px] grid-cols-1 gap-4 overflow-y-auto">
              {nw.owner_balances.map((owner) => (
                <OwnerBalanceMiniList key={owner.owner} owner={owner} maxBalance={maxOwnerAccountBalance} />
              ))}
            </div>
          </div>
        )}

        {/* Income Sources -- built from the same `LabeledBarRow` as Owner
            Balances (aligned label column, same row height, same `title`
            hover-for-full-name behavior, same `max-h-[420px]` scroll cap) so
            the two paired cards read as the same size instead of a plain-HTML
            list next to a Recharts chart with its own independent sizing. */}
        {sortedIncomeBreakdown.length > 0 && (
          <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
            <h3 className="mb-4 text-base sm:text-lg font-semibold text-ink">Income Sources</h3>
            <div className="max-h-[420px] space-y-1.5 overflow-y-auto">
              {sortedIncomeBreakdown.map((source, index) => (
                <LabeledBarRow
                  key={`${source.description}-${index}`}
                  label={source.description}
                  fullLabel={source.description}
                  value={source.amount}
                  pct={maxIncomeAmount > 0 ? Math.min(1, source.amount / maxIncomeAmount) : 0}
                  color={incomeColor()}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Additional Metrics -- all three tiles are the same MetricTile shape
          (no `metric` prop), so not stretch-broken today; `items-start` added
          for the same defense-in-depth reason as the Income/Expenses row above. */}
      <div className="grid grid-cols-1 items-start gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
