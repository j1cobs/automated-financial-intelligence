/**
 * Two-column (income / expenses) breakdown of one period's transactions,
 * opened by clicking a bar on either "Income vs Expenses" chart (monthly or
 * weekly) in `CashFlowTab.tsx`. Generalized from a weekly-only
 * `WeeklyTransactionsPreview` -- both charts share the same `FlowBarChart`
 * component and the same drill-down shape, just a different date-range
 * parser (`parseWeekRange` vs `parseMonthRange` in `lib/dateRanges.ts`), so
 * the caller resolves `{ label, dateFrom, dateTo }` and this component stays
 * agnostic to which chart opened it.
 *
 * Deliberately its own one-off query against `/ledger` rather than
 * `useLedger()`: `useLedger()` is wired to the global `FilterContext`, so
 * reusing it here would refetch on every unrelated filter change and would
 * require mutating the user's actual dashboard filters just to preview one
 * period.
 *
 * `LedgerItem` (see `lib/types.ts`) carries no `tx_type` field -- unlike the
 * aggregate endpoints, the ledger only has `amount`, so the income/expense
 * split here follows the same sign convention `TransactionsTab.tsx`'s
 * `AmountCell` and its "Positive amounts are income or credits. Negative
 * amounts are expenses or debits." caption already document.
 *
 * Within each column, transactions are grouped by `description` (not
 * `category` -- the ML classifier is still a Phase-1 stub per `CLAUDE.md`, so
 * `category` is `"uncategorized"` for virtually every real transaction, and
 * grouping by it would collapse everything into one bucket). This mirrors
 * how the Home tab's "Top Merchants" insight already aggregates. Groups are
 * sorted by subtotal magnitude descending, biggest contributor first,
 * regardless of column sign. The count + net total above each column reuses
 * `TransactionsTab.tsx`'s `AmountCell` -- the same "N transactions · Net $X"
 * pattern as the ledger summary line, exported from there for reuse.
 *
 * Interaction pattern mirrors `MultiSelectPopover.tsx`: Escape closes,
 * outside-click closes. There's no persistent trigger `<button>` to refocus
 * on close (the trigger is an SVG bar, not a focusable element), so on open
 * this dialog moves focus to its own close button instead.
 */

import { useEffect, useMemo, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { toSearchParams, type DashboardFilters } from '../lib/filters';
import { useFilters } from '../lib/FilterContext';
import { monthsCoveringRange } from '../lib/dateRanges';
import { groupByDescription } from '../lib/transactionGrouping';
import { AmountCell } from './TransactionsTab';
import type { LedgerResponse, LedgerItem } from '../lib/types';

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount);
}

interface PeriodTransactionsPreviewProps {
  /** Human-readable heading, e.g. "Week of 2024-01-08 – 2024-01-14" or
   *  "August 2026". Caller-supplied so this component never has to guess
   *  whether it opened from the weekly or monthly chart. */
  label: string;
  dateFrom: string;
  dateTo: string;
  onClose: () => void;
}

function TransactionColumn({
  title,
  titleClassName,
  transactions,
}: {
  title: string;
  titleClassName: string;
  transactions: LedgerItem[];
}) {
  const groups = useMemo(() => groupByDescription(transactions), [transactions]);
  const net = useMemo(() => transactions.reduce((total, tx) => total + tx.amount, 0), [transactions]);

  return (
    <div className="min-w-0">
      <h4 className={`mb-1 text-sm font-semibold ${titleClassName}`}>{title}</h4>
      {transactions.length === 0 ? (
        <p className="text-xs text-ink-muted">None</p>
      ) : (
        <>
          <p className="mb-2 flex flex-wrap items-baseline gap-x-1.5 text-xs font-medium text-ink-secondary">
            <span>
              {transactions.length} {transactions.length === 1 ? 'transaction' : 'transactions'}
            </span>
            <span aria-hidden="true">·</span>
            <span>
              Net <AmountCell amount={net} />
            </span>
          </p>
          <ul className="space-y-1.5">
            {groups.map((group) => (
              <li key={group.description} className="flex items-baseline justify-between gap-2 text-xs">
                <span className="min-w-0 truncate text-ink-secondary">
                  {group.description}
                  {group.count > 1 && <span className="text-ink-muted"> ×{group.count}</span>}
                </span>
                <span className="shrink-0 tabular-nums text-ink">{formatCurrency(group.amount)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export function PeriodTransactionsPreview({
  label,
  dateFrom,
  dateTo,
  onClose,
}: PeriodTransactionsPreviewProps) {
  const { filters } = useFilters();
  const containerRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeButtonRef.current?.focus();
  }, []);

  useEffect(() => {
    function onPointerDown(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        onClose();
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose();
      }
    }
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [onClose]);

  const overrideFilters: DashboardFilters = {
    ...filters,
    period: 'custom',
    months: monthsCoveringRange(dateFrom, dateTo),
    date_from: dateFrom,
    date_to: dateTo,
  };

  const { data, isLoading, isError } = useQuery({
    queryKey: ['ledger-preview', `${dateFrom}_${dateTo}`],
    queryFn: () => {
      const qs = toSearchParams(overrideFilters).toString();
      return apiFetch<LedgerResponse>(qs ? `/ledger?${qs}` : '/ledger');
    },
  });

  const transactions = data?.transactions ?? [];
  const income = transactions.filter((tx) => tx.amount >= 0);
  const expenses = transactions.filter((tx) => tx.amount < 0);

  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-4">
      <div
        ref={containerRef}
        role="dialog"
        aria-label={`Transactions for ${label}`}
        className="max-h-[80vh] w-full max-w-2xl overflow-auto rounded-lg border border-hairline bg-surface-1 p-4 shadow-lg sm:p-6"
      >
        <div className="mb-3 flex items-start justify-between gap-4">
          <h3 className="text-base font-semibold text-ink sm:text-lg">{label}</h3>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-md border border-hairline px-2 py-1 text-xs text-ink-secondary hover:text-ink"
          >
            Close
          </button>
        </div>

        {isLoading && <p className="text-sm text-ink-muted">Loading…</p>}
        {isError && <p className="text-sm text-neg-text">Failed to load transactions for this period.</p>}

        {data && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <TransactionColumn title="Income" titleClassName="text-flow-income" transactions={income} />
            <TransactionColumn title="Expenses" titleClassName="text-flow-expense" transactions={expenses} />
          </div>
        )}
      </div>
    </div>
  );
}
