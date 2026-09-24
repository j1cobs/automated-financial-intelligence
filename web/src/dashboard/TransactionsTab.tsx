import { useMemo, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { TooltipContentProps } from 'recharts';
import { useLedger, useAnomalies, useCategories } from '../lib/queries';
import {
  useUpdateCategory,
  useUpdateRecurring,
  useUpdateStreamRecurring,
  useUpdateDuplicate,
  useLinkTransaction,
  useUnlinkTransaction,
} from '../lib/mutations';
import type { LedgerItem, AnomalyItem } from '../lib/types';
import { formatCategory } from '../lib/categories';
import {
  categoricalColor,
  CATEGORICAL_SLOTS,
  gridProps,
  xAxisProps,
  yAxisProps,
  legendProps,
  CHART_MARGIN,
} from './chartTheme';
import { TabSkeleton, ErrorState } from './LoadingState';
import { strings } from '../lib/strings';
import { directionOf, toneFor, toneLabel, DIRECTION_GLYPH, TONE_TOKENS } from '../lib/polarity';
import type { TabId } from './tabs';
import { Button } from '../components/Button';

/**
 * Transactions tab -- ledger + anomaly scatter (PLAN.md Phase 15, Fix 10).
 *
 * The ledger row-rendering below `VIRTUALIZE_THRESHOLD` transactions is a
 * plain `<tbody>` map, identical to Phase 15's original markup -- every
 * existing ledger test exercises small fixtures and stays on this path
 * untouched. Above the threshold (a real account's history, e.g. 592 rows)
 * it switches to `@tanstack/react-virtual`, which only mounts the rows in the
 * scrolled viewport. `table-layout: fixed` + an explicit `<colgroup>` keeps
 * column widths stable as rows scroll in and out, since natural auto-layout
 * can't see the width of a row that isn't mounted.
 */

const UNCATEGORIZED_LABEL = 'Uncategorized';
/** The scatter is an all-pairs colour form (any two bubbles can sit side by
 *  side), so the tail folds into a shared "Other" slot rather than growing
 *  past the palette -- see `dataviz` skill, `color-formula.md` check 4. One
 *  slot is reserved for "Other", leaving `CATEGORICAL_SLOTS - 1` named ones. */
const MAX_NAMED_CATEGORIES = CATEGORICAL_SLOTS - 1;
const OTHER_LABEL = 'Other';

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function formatAxisDate(timestamp: number): string {
  return new Date(timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/**
 * Amount with polarity: colour never rides alone -- every coloured amount
 * ships a direction glyph and an sr-only label per the design system's
 * semantic-colour rule (see `lib/polarity.ts`).
 */
export function AmountCell({ amount }: { amount: number }) {
  const direction = directionOf(amount);
  const tone = toneFor(amount, 'normal');
  const tokens = TONE_TOKENS[tone];
  return (
    <span
      className="inline-flex items-center justify-end gap-1 font-mono tabular-nums"
      style={{ color: tokens.text }}
    >
      <span aria-hidden="true">{DIRECTION_GLYPH[direction]}</span>
      {formatCurrency(amount)}
      <span className="sr-only">({toneLabel(direction, tone)})</span>
    </span>
  );
}

/** Deterministic category -> colour slot, with a shared "Other" bucket past
 *  the palette's named-slot budget. Order is alphabetical over the full
 *  category set that's actually on screen, so two renders of the same data
 *  agree; it can still shift if a filter changes the category set, which is
 *  the accepted cost of an unbounded category list on an 8-slot palette. */
function useCategoryColorScale(categories: readonly (string | null)[]) {
  return useMemo(() => {
    const labels = Array.from(new Set(categories.map((c) => (c && c.trim() ? c : UNCATEGORIZED_LABEL)))).sort(
      (a, b) => a.localeCompare(b),
    );
    const named = labels.slice(0, MAX_NAMED_CATEGORIES);
    const overflow = labels.length > MAX_NAMED_CATEGORIES;
    const colorOf = (label: string): { bucket: string; color: string } => {
      const idx = named.indexOf(label);
      if (idx >= 0) return { bucket: label, color: categoricalColor(idx) };
      return { bucket: OTHER_LABEL, color: categoricalColor(MAX_NAMED_CATEGORIES) };
    };
    const buckets = overflow ? [...named, OTHER_LABEL] : named;
    return { colorOf, buckets };
  }, [categories]);
}

type ScatterPoint = {
  x: number;
  y: number;
  z: number;
  date: string;
  description: string;
  amount: number;
  owner_name: string | null;
  category: string;
  bucket: string;
  color: string;
};

function AnomalyTooltip({ active, payload }: Partial<TooltipContentProps<number, string>>) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0]?.payload as ScatterPoint | undefined;
  if (!point) return null;
  return (
    <div className="rounded-md border border-hairline bg-surface-1 p-2 text-xs shadow-sm sm:text-sm">
      <p className="mb-1 font-semibold text-ink">{point.description}</p>
      <p className="text-ink-secondary">
        {formatDate(point.date)} · {formatCategory(point.category)}
      </p>
      <p className="text-ink-secondary">{formatCurrency(point.amount)}</p>
      {point.owner_name && <p className="text-ink-muted">{point.owner_name}</p>}
    </div>
  );
}

function AnomalyScatter({ anomalies }: { anomalies: AnomalyItem[] }) {
  const { colorOf, buckets } = useCategoryColorScale(anomalies.map((a) => a.category));

  const points: ScatterPoint[] = useMemo(
    () =>
      anomalies.map((a) => {
        const label = a.category && a.category.trim() ? a.category : UNCATEGORIZED_LABEL;
        const { bucket, color } = colorOf(label);
        return {
          x: new Date(a.date).getTime(),
          y: a.outlier_score,
          z: Math.abs(a.amount),
          date: a.date,
          description: a.description,
          amount: a.amount,
          owner_name: a.owner_name,
          category: label,
          bucket,
          color,
        };
      }),
    [anomalies, colorOf],
  );

  const byBucket = useMemo(() => {
    const map = new Map<string, ScatterPoint[]>();
    for (const point of points) {
      const list = map.get(point.bucket) ?? [];
      list.push(point);
      map.set(point.bucket, list);
    }
    return buckets
      .map((bucket) => ({ bucket, points: map.get(bucket) ?? [] }))
      .filter((s) => s.points.length > 0);
  }, [points, buckets]);

  return (
    <div className="h-72 w-full sm:h-96">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={CHART_MARGIN.default}>
          <CartesianGrid {...gridProps()} />
          <XAxis
            {...xAxisProps()}
            dataKey="x"
            type="number"
            name="Date"
            domain={['dataMin', 'dataMax']}
            tickFormatter={(value: number) => formatAxisDate(value)}
          />
          <YAxis {...yAxisProps()} dataKey="y" type="number" name="Outlier score" />
          <ZAxis dataKey="z" type="number" range={[80, 900]} name="Amount" />
          <Tooltip content={<AnomalyTooltip />} cursor={{ strokeDasharray: '3 3' }} />
          {byBucket.length > 1 && <Legend {...legendProps()} />}
          {byBucket.map(({ bucket, points: bucketPoints }) => (
            <Scatter
              key={bucket}
              name={formatCategory(bucket)}
              data={bucketPoints}
              fill={bucketPoints[0]?.color}
              fillOpacity={0.75}
            />
          ))}
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

type SortKey = 'date' | 'amount' | 'description';
type SortDir = 'asc' | 'desc';

function sortTransactions(rows: LedgerItem[], key: SortKey, dir: SortDir): LedgerItem[] {
  const sign = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    switch (key) {
      case 'amount':
        return (a.amount - b.amount) * sign;
      case 'description':
        return a.description.localeCompare(b.description) * sign;
      case 'date':
      default:
        return (new Date(a.date).getTime() - new Date(b.date).getTime()) * sign;
    }
  });
}

function SortButton({
  label,
  active,
  dir,
  onClick,
  align = 'left',
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
  align?: 'left' | 'right';
}) {
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={onClick}
      className={`min-h-0 w-full px-0 py-0 font-semibold ${
        align === 'right' ? 'justify-end' : 'justify-start'
      }`}
      aria-label={`Sort by ${label}`}
    >
      {label}
      <span aria-hidden="true" className={active ? 'text-ink' : 'text-ink-muted'}>
        {active ? (dir === 'asc' ? '▲' : '▼') : '↕'}
      </span>
    </Button>
  );
}

// Above this many rows, mounting every `<tr>` at once is real DOM weight for
// no benefit -- switch to a virtualized window. Below it, every existing
// ledger test's small fixture stays on the plain, unvirtualized path.
const VIRTUALIZE_THRESHOLD = 50;
// A ledger row is single-line except when it carries an owner-name subtext
// or the "Excluded" duplicate badge, both of which wrap onto a second line
// only rarely -- this is a deliberate estimate, not a hard height; the
// virtualizer's own `measureElement` corrects it per-row after mount.
const ROW_HEIGHT_ESTIMATE = 45;

/** The header `<tr>`, shared by the plain and virtualized paths so the two
 *  can never drift out of sync with each other. */
function LedgerTheadRow({
  sortKey,
  sortDir,
  toggleSort,
  showPfcDetail,
}: {
  sortKey: SortKey;
  sortDir: SortDir;
  toggleSort: (key: SortKey) => void;
  showPfcDetail: boolean;
}) {
  return (
    <tr className="border-b border-hairline bg-surface-2">
      <th className="px-2 py-2 text-left sm:px-4 sm:py-3">
        <SortButton
          label="Date"
          active={sortKey === 'date'}
          dir={sortDir}
          onClick={() => toggleSort('date')}
        />
      </th>
      <th className="px-2 py-2 text-left font-semibold text-ink-secondary sm:px-4 sm:py-3">Account</th>
      <th className="px-2 py-2 text-left sm:px-4 sm:py-3">
        <SortButton
          label="Description"
          active={sortKey === 'description'}
          dir={sortDir}
          onClick={() => toggleSort('description')}
        />
      </th>
      <th className="px-2 py-2 text-right sm:px-4 sm:py-3">
        <SortButton
          label="Amount"
          active={sortKey === 'amount'}
          dir={sortDir}
          onClick={() => toggleSort('amount')}
          align="right"
        />
      </th>
      <th className="px-2 py-2 text-left font-semibold text-ink-secondary sm:px-4 sm:py-3">Category</th>
      {showPfcDetail && (
        <th className="px-2 py-2 text-left font-semibold text-ink-secondary sm:px-4 sm:py-3">Plaid detail</th>
      )}
      <th className="px-2 py-2 text-center font-semibold text-ink-secondary sm:px-4 sm:py-3">Recurring</th>
      <th className="px-2 py-2 text-center font-semibold text-ink-secondary sm:px-4 sm:py-3">Duplicate</th>
      <th className="px-2 py-2 text-center font-semibold text-ink-secondary sm:px-4 sm:py-3">Link</th>
    </tr>
  );
}

interface LedgerRowProps {
  tx: LedgerItem;
  editingHash: string | null;
  editingCategory: string;
  categories: string[] | undefined;
  isRecurringPending: boolean;
  isDuplicatePending: boolean;
  isLinkPending: boolean;
  showPfcDetail: boolean;
  linkingHash: string | null;
  selectedLinkedHash: string | null;
  allTransactions: LedgerItem[];
  onStartEdit: (hash: string, category: string) => void;
  onCategoryChange: (hash: string, category: string) => void;
  onStopEdit: () => void;
  onToggleRecurring: (hash: string, current: boolean) => void;
  onToggleStreamRecurring: (streamId: string, current: boolean) => void;
  onToggleDuplicate: (hash: string, current: boolean) => void;
  onStartLinking: (hash: string | null) => void;
  onSelectLinkedHash: (hash: string) => void;
  onLink: (hash: string, otherHash: string) => void;
  onUnlink: (hash: string) => void;
}

function LedgerRow({
  tx,
  editingHash,
  editingCategory,
  categories,
  isRecurringPending,
  isDuplicatePending,
  isLinkPending,
  showPfcDetail,
  linkingHash,
  selectedLinkedHash,
  allTransactions,
  onStartEdit,
  onCategoryChange,
  onStopEdit,
  onToggleRecurring,
  onToggleStreamRecurring,
  onToggleDuplicate,
  onStartLinking,
  onSelectLinkedHash,
  onLink,
  onUnlink,
}: LedgerRowProps) {
  return (
    <tr
      className={`border-b border-hairline ${
        tx.is_duplicate ? 'bg-surface-2 text-ink-muted' : 'hover:bg-surface-2'
      }`}
    >
      {/* Every cell clips rather than overflows. With `tableLayout: fixed` an
          unconstrained cell renders past its column edge and over whatever sits
          to its right, which is what made the Recurring and Duplicate controls
          unreadable once the Plaid-detail column appeared. `title` keeps the
          full value reachable on hover wherever it can be clipped. */}
      <td className="truncate px-2 py-2 sm:px-4 sm:py-3" title={formatDate(tx.date)}>
        {formatDate(tx.date)}
      </td>
      <td className="px-2 py-2 sm:px-4 sm:py-3">
        <div className="truncate" title={tx.account_name}>
          {tx.account_name}
        </div>
        {tx.owner_name && (
          <div className="truncate text-xs text-ink-muted" title={tx.owner_name}>
            {tx.owner_name}
          </div>
        )}
      </td>
      <td className={`px-2 py-2 sm:px-4 sm:py-3 ${tx.is_duplicate ? 'line-through' : ''}`}>
        <div className="flex items-center gap-2">
          <span className="truncate" title={tx.description}>
            {tx.description}
          </span>
          {tx.is_duplicate && (
            <span className="shrink-0 rounded-full border border-hairline px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-ink-muted">
              Excluded
            </span>
          )}
        </div>
      </td>
      <td className="truncate px-2 py-2 text-right sm:px-4 sm:py-3">
        <AmountCell amount={tx.amount} />
      </td>
      <td className="px-2 py-2 sm:px-4 sm:py-3">
        {editingHash === tx.hash ? (
          <select
            autoFocus
            value={editingCategory}
            onChange={(e) => onCategoryChange(tx.hash, e.target.value)}
            onBlur={onStopEdit}
            className="min-h-9 w-full rounded border border-hairline bg-surface-1 px-2 py-1 text-xs text-ink sm:text-sm"
          >
            {categories?.map((cat) => (
              <option key={cat} value={cat}>
                {formatCategory(cat)}
              </option>
            ))}
          </select>
        ) : (
          <Button
            variant="ghost"
            onClick={() => onStartEdit(tx.hash, tx.category || 'UNCATEGORIZED')}
            className="w-full justify-start px-2 text-ink hover:bg-surface-3"
          >
            <span className="truncate">
              {tx.category ? formatCategory(tx.category) : <span className="text-ink-muted">—</span>}
            </span>
          </Button>
        )}
      </td>
      {showPfcDetail && (
        <td
          className={`px-2 py-2 sm:px-4 sm:py-3 ${tx.category_source === 'merchant' ? 'bg-surface-2' : ''}`}
        >
          {/* The column this whole phase is about: `pfc_detailed` values are
              long (`FOOD_AND_DRINK_FAST_FOOD`), so without clipping this cell
              ran straight over Recurring and Duplicate. */}
          <div className="truncate" title={tx.pfc_detailed ?? undefined}>
            {tx.pfc_detailed ? tx.pfc_detailed : <span className="text-ink-muted">—</span>}
          </div>
        </td>
      )}
      {/* Two different consequences behind one column, so they must look
          different BEFORE the click: a row in a detected series toggles the
          whole series, a standalone row toggles only itself. Previously both
          were an identical bare checkbox, which is why the same charge could
          be flagged over and over, once per occurrence. */}
      <td className="px-2 py-2 text-center sm:px-4 sm:py-3">
        <label className="flex flex-col items-center gap-0.5">
          <input
            type="checkbox"
            checked={tx.is_recurring}
            onChange={() =>
              tx.stream_id
                ? onToggleStreamRecurring(tx.stream_id, tx.is_recurring)
                : onToggleRecurring(tx.hash, tx.is_recurring)
            }
            disabled={isRecurringPending}
            className="h-5 w-5 cursor-pointer"
            aria-label={
              tx.stream_id
                ? `Mark the whole ${tx.stream_description ?? tx.description} series as ${
                    tx.is_recurring ? 'non-recurring' : 'recurring'
                  }`
                : `Mark ${tx.description} as ${tx.is_recurring ? 'non-recurring' : 'recurring'} (this row only)`
            }
          />
          <span className="text-[10px] leading-tight text-ink-muted">
            {tx.stream_id ? 'series' : 'this row'}
          </span>
        </label>
      </td>
      <td className="px-2 py-2 text-center sm:px-4 sm:py-3">
        <input
          type="checkbox"
          checked={tx.is_duplicate}
          onChange={() => onToggleDuplicate(tx.hash, tx.is_duplicate)}
          disabled={isDuplicatePending}
          className="h-5 w-5 cursor-pointer"
          aria-label={`Mark ${tx.description} as ${tx.is_duplicate ? 'not a duplicate' : 'duplicate'}`}
        />
      </td>
      <td className="px-2 py-2 text-center sm:px-4 sm:py-3">
        {linkingHash === tx.hash ? (
          // Picker mode: show dropdown with candidate transactions
          (() => {
            // Filter candidates: opposite sign, not self, not already linked
            const candidates = allTransactions
              .filter(
                (candidate) =>
                  candidate.hash !== tx.hash && // not self
                  Math.sign(candidate.amount) !== Math.sign(tx.amount) && // opposite sign
                  !candidate.linked_transaction_hash, // not already linked
              )
              // Sort by closest amount first, then by closest date as a tie-break --
              // the amount is usually the stronger signal for which transaction is the
              // actual matching reimbursement/expense.
              .sort((a, b) => {
                const txAmount = Math.abs(tx.amount);
                const aAmountDistance = Math.abs(Math.abs(a.amount) - txAmount);
                const bAmountDistance = Math.abs(Math.abs(b.amount) - txAmount);
                if (aAmountDistance !== bAmountDistance) {
                  return aAmountDistance - bAmountDistance;
                }
                const txDate = new Date(tx.date).getTime();
                const aDate = new Date(a.date).getTime();
                const bDate = new Date(b.date).getTime();
                return Math.abs(aDate - txDate) - Math.abs(bDate - txDate);
              });

            return (
              <div className="flex flex-col gap-1">
                <select
                  autoFocus
                  value={selectedLinkedHash || ''}
                  onChange={(e) => onSelectLinkedHash(e.target.value)}
                  className="min-h-9 rounded border border-hairline bg-surface-1 px-2 py-1 text-xs sm:text-sm"
                >
                  <option value="">Select transaction</option>
                  {candidates.map((candidate) => (
                    <option key={candidate.hash} value={candidate.hash}>
                      {formatDate(candidate.date)} • {candidate.description} •{' '}
                      {formatCurrency(candidate.amount)}
                    </option>
                  ))}
                </select>
                {candidates.length > 0 && selectedLinkedHash && (
                  <Button
                    size="sm"
                    onClick={() => onLink(tx.hash, selectedLinkedHash)}
                    disabled={isLinkPending}
                    className="min-h-0 px-1.5 py-0.5 hover:bg-surface-3 sm:text-sm"
                  >
                    Confirm
                  </Button>
                )}
                <Button
                  size="sm"
                  onClick={() => onStartLinking(null)}
                  className="min-h-0 px-1.5 py-0.5 text-ink-secondary sm:text-sm"
                >
                  Cancel
                </Button>
              </div>
            );
          })()
        ) : tx.linked_transaction_hash ? (
          // Linked state: show "Linked" label and "Unlink" button
          <div className="flex flex-col items-center gap-1">
            <span className="text-xs font-medium text-ink-secondary">Linked</span>
            <Button
              size="sm"
              onClick={() => onUnlink(tx.hash)}
              disabled={isLinkPending}
              className="min-h-0 px-1.5 py-0.5 hover:bg-surface-3 sm:text-sm"
            >
              Unlink
            </Button>
          </div>
        ) : (
          // Unlinked state: show "Link" button
          <Button
            size="sm"
            onClick={() => onStartLinking(tx.hash)}
            disabled={isLinkPending}
            className="min-h-0 hover:bg-surface-3 sm:text-sm"
          >
            Link
          </Button>
        )}
      </td>
    </tr>
  );
}

/**
 * The ledger's column widths, as percentages, in render order:
 * Date, Account, Description, Amount, Category, [Plaid detail], Recurring,
 * Duplicate, Link.
 *
 * Each set must sum to exactly 100 (pinned by a test). The previous sets
 * summed to 103 and 114: with `tableLayout: fixed` the browser rescales an
 * over-declared colgroup proportionally, so turning the Plaid-detail column on
 * silently shrank every other column by ~12% and cells without `truncate`
 * spilled into their neighbours. That is the "columns overlap when category
 * detail is shown" bug -- it was arithmetic, not CSS.
 */
export const LEDGER_COLUMN_WIDTHS = {
  withoutDetail: [10, 14, 26, 12, 13, 9, 8, 8],
  withDetail: [9, 12, 22, 11, 12, 12, 8, 7, 7],
} as const;

/** Fixed column widths so a row scrolled out of the virtualized viewport
 *  doesn't shift the ones still mounted -- natural auto-layout sizes columns
 *  from whatever rows happen to be in the DOM, which changes every scroll
 *  frame once rows unmount. Applied to *both* ledger paths: the plain
 *  (<50-row) table previously had no colgroup and no fixed layout at all, so
 *  its columns were sized by whatever content happened to be present. */
function LedgerColgroup({ showPfcDetail }: { showPfcDetail: boolean }) {
  const widths = showPfcDetail
    ? LEDGER_COLUMN_WIDTHS.withDetail
    : LEDGER_COLUMN_WIDTHS.withoutDetail;
  return (
    <colgroup>
      {widths.map((width, index) => (
        // Percentages are computed, so they go in `style`: Tailwind can only
        // emit classes it can see as literals at build time.
        <col key={index} style={{ width: `${width}%` }} />
      ))}
    </colgroup>
  );
}

interface VirtualizedLedgerTableProps extends Omit<LedgerRowProps, 'tx'> {
  transactions: LedgerItem[];
  sortKey: SortKey;
  sortDir: SortDir;
  toggleSort: (key: SortKey) => void;
  showPfcDetail: boolean;
}

/** The large-ledger path: a fixed-height scroll container with a sticky
 *  header and only the on-screen rows mounted. Uses the padding-row
 *  technique (a leading and trailing spacer `<tr>`, sized to the scrolled-
 *  past total) rather than absolutely-positioning each row -- every mounted
 *  row is a genuine `<tr>` in normal table flow, so `<colgroup>` widths and
 *  native table layout behave exactly like the plain path. */
function VirtualizedLedgerTable({
  transactions,
  sortKey,
  sortDir,
  toggleSort,
  showPfcDetail,
  ...rowProps
}: VirtualizedLedgerTableProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: transactions.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT_ESTIMATE,
    overscan: 10,
  });
  const virtualRows = rowVirtualizer.getVirtualItems();
  const paddingTop = virtualRows.length > 0 ? virtualRows[0].start : 0;
  const paddingBottom =
    virtualRows.length > 0 ? rowVirtualizer.getTotalSize() - virtualRows[virtualRows.length - 1].end : 0;

  const colSpan = showPfcDetail ? 9 : 8;

  return (
    <div ref={scrollRef} className="max-h-[70vh] overflow-auto rounded-lg border border-hairline">
      <table
        className="w-full min-w-[720px] text-xs sm:text-sm"
        style={{ tableLayout: 'fixed' }}
      >
        <LedgerColgroup showPfcDetail={showPfcDetail} />
        <thead className="sticky top-0 z-10">
          <LedgerTheadRow
            sortKey={sortKey}
            sortDir={sortDir}
            toggleSort={toggleSort}
            showPfcDetail={showPfcDetail}
          />
        </thead>
        <tbody>
          {paddingTop > 0 && (
            <tr aria-hidden="true" style={{ height: `${paddingTop}px` }}>
              <td colSpan={colSpan} />
            </tr>
          )}
          {virtualRows.map((virtualRow) => (
            <LedgerRow
              key={transactions[virtualRow.index].hash}
              tx={transactions[virtualRow.index]}
              showPfcDetail={showPfcDetail}
              {...rowProps}
            />
          ))}
          {paddingBottom > 0 && (
            <tr aria-hidden="true" style={{ height: `${paddingBottom}px` }}>
              <td colSpan={colSpan} />
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

/** Labels for the "Back to X" drill-down-return button. Mirrors
 *  `Dashboard.tsx`'s `TABS` labels -- kept local rather than shared, since
 *  each tab component here is otherwise self-contained (see that file's own
 *  comment on the pattern) and only one extra string is at stake. */
const TAB_LABELS: Record<TabId, string> = {
  overview: 'Overview',
  cashflow: 'Cash Flow',
  budget: 'Budget',
  transactions: 'Transactions',
};

interface TransactionsTabProps {
  /** Set when the user arrived here via a cross-tab drill-down (e.g. the
   *  Cash Flow rolling-30-day-spend chart) -- renders a "Back to X" button
   *  that restores the tab + filters snapshotted before the drill-down.
   *  `dateRangeLabel` is display-only (Item 3) -- a human-readable rendering
   *  of the snapshotted `date_from`/`date_to`, when the drill-down set them,
   *  so this area can state the active range explicitly rather than relying
   *  solely on the FilterBar chip. */
  returnTo?: { tab: TabId; dateRangeLabel?: string | null } | null;
  onReturn?: () => void;
}

export function TransactionsTab({ returnTo = null, onReturn }: TransactionsTabProps) {
  const ledgerQuery = useLedger();
  const anomaliesQuery = useAnomalies();
  const categoriesQuery = useCategories();

  const updateCategory = useUpdateCategory();
  const updateRecurring = useUpdateRecurring();
  const updateStreamRecurring = useUpdateStreamRecurring();
  const updateDuplicate = useUpdateDuplicate();
  const linkTransaction = useLinkTransaction();
  const unlinkTransaction = useUnlinkTransaction();

  const [editingHash, setEditingHash] = useState<string | null>(null);
  const [editingCategory, setEditingCategory] = useState<string>('');
  const [sortKey, setSortKey] = useState<SortKey>('date');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [linkingHash, setLinkingHash] = useState<string | null>(null);
  const [selectedLinkedHash, setSelectedLinkedHash] = useState<string | null>(null);
  const [showPfcDetail, setShowPfcDetail] = useState(() => {
    try {
      const stored = localStorage.getItem('showPfcDetailColumn');
      return stored === 'true';
    } catch {
      return false;
    }
  });

  const handleTogglePfcDetail = (newValue: boolean) => {
    setShowPfcDetail(newValue);
    try {
      localStorage.setItem('showPfcDetailColumn', String(newValue));
    } catch {
      // silently fail if localStorage is unavailable
    }
  };

  // Ledger edits are optimistic (see `lib/mutations.ts`): the row updates before the
  // request resolves, and a failure rolls it back via the mutation's own onError. The
  // rollback is silent to the row itself, so this banner is what actually tells the
  // user the edit didn't take -- swallowing the rejection here would otherwise leave
  // an unhandled promise rejection with `mutateAsync` and no visible failure at all.
  const editFailed =
    updateCategory.isError ||
    updateRecurring.isError ||
    updateDuplicate.isError ||
    linkTransaction.isError ||
    unlinkTransaction.isError;

  // Merchant-memory backfill confirmation (PLAN.md Phase 18, Step 4): the API
  // reports how many other rows from the same merchant it just recategorized
  // along with this edit. Most corrections backfill nothing -- silent then.
  const backfilledCount = updateCategory.isSuccess ? (updateCategory.data?.backfilled_count ?? 0) : 0;

  const handleCategoryChange = async (hash: string, newCategory: string) => {
    setEditingHash(null);
    try {
      await updateCategory.mutateAsync({ hash, category: newCategory });
    } catch {
      /* surfaced via updateCategory.isError below */
    }
  };

  const handleRecurringToggle = async (hash: string, currentValue: boolean) => {
    try {
      await updateRecurring.mutateAsync({ hash, recurring: !currentValue });
    } catch {
      /* surfaced via updateRecurring.isError below */
    }
  };

  const handleStreamRecurringToggle = async (streamId: string, currentValue: boolean) => {
    try {
      await updateStreamRecurring.mutateAsync({ streamId, recurring: !currentValue });
    } catch {
      /* surfaced via updateStreamRecurring.isError below */
    }
  };

  const handleDuplicateToggle = async (hash: string, currentValue: boolean) => {
    try {
      await updateDuplicate.mutateAsync({ hash, duplicate: !currentValue });
    } catch {
      /* surfaced via updateDuplicate.isError below */
    }
  };

  const handleStartLinking = (hash: string | null) => {
    setLinkingHash(hash);
    setSelectedLinkedHash(null);
  };

  const handleSelectLinkedHash = (hash: string) => {
    setSelectedLinkedHash(hash);
  };

  const handleLink = async (hash: string, otherHash: string) => {
    try {
      await linkTransaction.mutateAsync({ hash, otherHash });
      setLinkingHash(null);
      setSelectedLinkedHash(null);
    } catch {
      /* surfaced via linkTransaction.isError below */
    }
  };

  const handleUnlink = async (hash: string) => {
    try {
      await unlinkTransaction.mutateAsync(hash);
    } catch {
      /* surfaced via unlinkTransaction.isError below */
    }
  };

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir(key === 'description' ? 'asc' : 'desc');
    }
  };

  const sortedTransactions = useMemo(
    () => (ledgerQuery.data ? sortTransactions(ledgerQuery.data.transactions, sortKey, sortDir) : []),
    [ledgerQuery.data, sortKey, sortDir],
  );

  const ledgerSummary = useMemo(() => {
    const count = sortedTransactions.length;
    const sum = sortedTransactions.reduce((total, tx) => total + tx.amount, 0);
    return { count, sum };
  }, [sortedTransactions]);

  return (
    <div className="space-y-6 sm:space-y-8">
      {returnTo && onReturn && (
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onReturn}
            className="flex min-h-9 items-center gap-1 rounded-md border border-hairline px-3 py-1.5 text-xs font-medium text-ink-secondary hover:text-ink sm:text-sm"
          >
            <span aria-hidden="true">←</span> Back to {TAB_LABELS[returnTo.tab]}
          </button>
          {returnTo.dateRangeLabel && (
            <span className="text-xs text-ink-muted">Showing {returnTo.dateRangeLabel}</span>
          )}
        </div>
      )}

      {/* Anomalies Section */}
      <div>
        <h2 className="mb-1 text-base font-semibold text-ink sm:text-lg">Anomalies</h2>

        {anomaliesQuery.isLoading && <TabSkeleton />}

        {anomaliesQuery.isError && (
          <ErrorState
            message="Failed to load anomalies. Please try again."
            onRetry={() => void anomaliesQuery.refetch()}
          />
        )}

        {anomaliesQuery.data && (
          <>
            {anomaliesQuery.data.anomalies.length === 0 ? (
              <div className="rounded-lg border border-hairline bg-surface-1 py-8 text-center text-sm text-ink-muted">
                No anomalies detected
              </div>
            ) : (
              <div className="rounded-lg border border-hairline bg-surface-1 p-3 sm:p-4">
                <p className="mb-2 text-xs text-ink-muted">Higher score = more unusual transaction.</p>
                <AnomalyScatter anomalies={anomaliesQuery.data.anomalies} />
              </div>
            )}
          </>
        )}
      </div>

      {/* Ledger Section */}
      <div>
        <h2 className="mb-1 text-base font-semibold text-ink sm:text-lg">Ledger</h2>
        <div className="mb-2 space-y-0.5 text-xs text-ink-muted">
          <p>
            Tick Duplicate to exclude a double-posted transaction from every total and chart. Flagged rows
            stay listed here so you can untick them.
          </p>
          <p>Edit categories inline — changes persist across pipeline re-runs.</p>
          <p>Positive amounts are income or credits. Negative amounts are expenses or debits.</p>
        </div>

        <div className="mb-2 flex items-center gap-2">
          <label className="flex items-center gap-2 text-xs text-ink-secondary sm:text-sm">
            <input
              type="checkbox"
              checked={showPfcDetail}
              onChange={(e) => handleTogglePfcDetail(e.target.checked)}
              className="h-4 w-4 cursor-pointer"
            />
            Show category detail
          </label>
        </div>

        {editFailed && (
          <div className="mb-2 rounded border border-neg bg-surface-2 px-3 py-2 text-xs text-neg-text sm:text-sm">
            {strings.loading.editFailed}
          </div>
        )}

        {!editFailed && backfilledCount > 0 && (
          <div className="mb-2 rounded border border-hairline bg-surface-2 px-3 py-2 text-xs text-ink-secondary sm:text-sm">
            {strings.ledger.categoryBackfilled(backfilledCount)}
          </div>
        )}

        {ledgerQuery.isLoading && <TabSkeleton />}

        {ledgerQuery.isError && (
          <ErrorState
            message="Failed to load transactions. Please try again."
            onRetry={() => void ledgerQuery.refetch()}
          />
        )}

        {ledgerQuery.data && (
          <div>
            <p className="mb-2 flex flex-wrap items-baseline gap-x-2 text-xs font-medium text-ink-secondary">
              <span>
                {ledgerSummary.count} {ledgerSummary.count === 1 ? 'transaction' : 'transactions'}
              </span>
              <span aria-hidden="true">·</span>
              <span>
                Net <AmountCell amount={ledgerSummary.sum} />
              </span>
            </p>
            {sortedTransactions.length > VIRTUALIZE_THRESHOLD ? (
              <VirtualizedLedgerTable
                transactions={sortedTransactions}
                sortKey={sortKey}
                sortDir={sortDir}
                toggleSort={toggleSort}
                showPfcDetail={showPfcDetail}
                editingHash={editingHash}
                editingCategory={editingCategory}
                categories={categoriesQuery.data?.categories}
                isRecurringPending={updateRecurring.isPending}
                isDuplicatePending={updateDuplicate.isPending}
                isLinkPending={linkTransaction.isPending || unlinkTransaction.isPending}
                linkingHash={linkingHash}
                selectedLinkedHash={selectedLinkedHash}
                allTransactions={sortedTransactions}
                onStartEdit={(hash, category) => {
                  setEditingHash(hash);
                  setEditingCategory(category);
                }}
                onCategoryChange={handleCategoryChange}
                onStopEdit={() => setEditingHash(null)}
                onToggleRecurring={handleRecurringToggle}
                onToggleStreamRecurring={handleStreamRecurringToggle}
                onToggleDuplicate={handleDuplicateToggle}
                onStartLinking={handleStartLinking}
                onSelectLinkedHash={handleSelectLinkedHash}
                onLink={handleLink}
                onUnlink={handleUnlink}
              />
            ) : (
              <div className="overflow-x-auto rounded-lg border border-hairline">
                {/* `min-w-[720px]`: with 8-9 fixed-percentage columns, a phone
                    viewport would squeeze each to a few characters. Scrolling
                    the table sideways inside its container keeps every column
                    readable instead. */}
                <table
                  className="w-full min-w-[720px] text-xs sm:text-sm"
                  style={{ tableLayout: 'fixed' }}
                >
                  <LedgerColgroup showPfcDetail={showPfcDetail} />
                  <thead>
                    <LedgerTheadRow
                      sortKey={sortKey}
                      sortDir={sortDir}
                      toggleSort={toggleSort}
                      showPfcDetail={showPfcDetail}
                    />
                  </thead>
                  <tbody>
                    {sortedTransactions.length === 0 ? (
                      <tr>
                        <td
                          colSpan={showPfcDetail ? 9 : 8}
                          className="px-2 py-6 text-center text-xs text-ink-muted sm:px-4 sm:py-8 sm:text-sm"
                        >
                          No transactions found
                        </td>
                      </tr>
                    ) : (
                      sortedTransactions.map((tx: LedgerItem) => (
                        <LedgerRow
                          key={tx.hash}
                          tx={tx}
                          editingHash={editingHash}
                          editingCategory={editingCategory}
                          categories={categoriesQuery.data?.categories}
                          isRecurringPending={updateRecurring.isPending}
                          isDuplicatePending={updateDuplicate.isPending}
                          isLinkPending={linkTransaction.isPending || unlinkTransaction.isPending}
                          showPfcDetail={showPfcDetail}
                          linkingHash={linkingHash}
                          selectedLinkedHash={selectedLinkedHash}
                          allTransactions={sortedTransactions}
                          onStartEdit={(hash, category) => {
                            setEditingHash(hash);
                            setEditingCategory(category);
                          }}
                          onCategoryChange={handleCategoryChange}
                          onStopEdit={() => setEditingHash(null)}
                          onToggleRecurring={handleRecurringToggle}
                          onToggleStreamRecurring={handleStreamRecurringToggle}
                          onToggleDuplicate={handleDuplicateToggle}
                          onStartLinking={handleStartLinking}
                          onSelectLinkedHash={handleSelectLinkedHash}
                          onLink={handleLink}
                          onUnlink={handleUnlink}
                        />
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
