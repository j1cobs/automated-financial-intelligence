/**
 * Sticky filter bar rendered under the tab nav (see `dashboard/Dashboard.tsx`).
 * Reads/writes filter state through `useFilters()` (`lib/FilterContext.tsx`)
 * — every data hook in `lib/queries.ts` picks up the same state automatically,
 * so this component never talks to `apiFetch` directly.
 *
 * Layout:
 *  - >= sm: period select + owner multi-select always visible, a month
 *    multi-select appears when period === 'custom', a "More filters" popover
 *    holds the rest, and active filters render as removable chips below.
 *  - < sm: everything collapses into a "Filters (N)" button that opens a
 *    bottom sheet with every control.
 */

import { useEffect, useRef, useState, type ChangeEvent, type ReactNode } from 'react';
import { useFilters } from '../lib/FilterContext';
import { useFilterOptions } from '../lib/queries';
import { activeFilterChips, countActiveFilters, PERIOD_LABELS, type PeriodPreset } from '../lib/filters';
import { MultiSelectPopover } from './MultiSelectPopover';
import type { FilterOptions } from '../lib/types';

const PERIOD_OPTIONS: PeriodPreset[] = [
  'last_30_days',
  'current_month',
  'last_3_months',
  'last_6_months',
  'ytd',
  'all_time',
  'custom',
];

const SEARCH_DEBOUNCE_MS = 300;

const selectClass =
  'min-h-9 rounded-md border border-hairline bg-surface-1 px-2 py-1 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-cat-1';
const labelClass = 'text-xs font-medium text-ink-secondary';
const fieldClass = 'flex flex-col gap-1';

export function FilterBar() {
  const { filters, setFilters, patchFilters, reset } = useFilters();
  const optionsQuery = useFilterOptions();
  const options: FilterOptions | undefined = optionsQuery.data;

  const [searchDraft, setSearchDraft] = useState(filters.search ?? '');
  // Tracks the last `filters.search` this component itself has seen, so an
  // *external* change (chip removal, Clear all, a pasted URL) can be told
  // apart from the draft simply catching up to what this component just
  // committed. Adjusted during render, not in an effect -- see "Adjusting
  // state when a prop changes" in the React docs; a synchronous setState
  // inside a plain effect body causes an avoidable extra render pass.
  const [lastSyncedSearch, setLastSyncedSearch] = useState(filters.search ?? '');
  if ((filters.search ?? '') !== lastSyncedSearch) {
    setLastSyncedSearch(filters.search ?? '');
    setSearchDraft(filters.search ?? '');
  }

  const [morePopoverOpen, setMorePopoverOpen] = useState(false);
  const [mobileSheetOpen, setMobileSheetOpen] = useState(false);
  const moreButtonRef = useRef<HTMLButtonElement>(null);

  // Debounce the free-text search so typing doesn't fire a request per keystroke.
  useEffect(() => {
    if (searchDraft === (filters.search ?? '')) return;
    const timeout = window.setTimeout(() => {
      patchFilters({ search: searchDraft || null });
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timeout);
    // Only re-run when the draft itself changes -- re-arming on every
    // `filters.search`/`patchFilters` identity change would reset the timer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchDraft]);

  useEffect(() => {
    if (!morePopoverOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMorePopoverOpen(false);
        moreButtonRef.current?.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [morePopoverOpen]);

  useEffect(() => {
    if (!mobileSheetOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMobileSheetOpen(false);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [mobileSheetOpen]);

  const chips = activeFilterChips(filters, options);
  const activeCount = countActiveFilters(filters);

  const onPeriodChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const period = event.target.value as PeriodPreset;
    patchFilters({ period, months: period === 'custom' ? filters.months : null });
  };

  function renderCoreControls(idPrefix: string): ReactNode {
    return (
      <>
        <div className={fieldClass}>
          <label htmlFor={`${idPrefix}-period`} className={labelClass}>
            Period
          </label>
          <select
            id={`${idPrefix}-period`}
            value={filters.period}
            onChange={onPeriodChange}
            className={selectClass}
          >
            {PERIOD_OPTIONS.map((preset) => (
              <option key={preset} value={preset}>
                {PERIOD_LABELS[preset]}
              </option>
            ))}
          </select>
        </div>

        <MultiSelectPopover
          id={`${idPrefix}-owners`}
          label="Owner"
          options={(options?.owners ?? []).map((owner) => ({ value: owner, label: owner }))}
          selected={filters.owners}
          onChange={(values) => patchFilters({ owners: values })}
          className="min-w-32"
        />

        {filters.period === 'custom' && (
          <MultiSelectPopover
            id={`${idPrefix}-months`}
            label="Months"
            options={(options?.months ?? []).map((month) => ({ value: month.key, label: month.label }))}
            selected={filters.months}
            onChange={(values) => patchFilters({ months: values })}
            className="min-w-40"
          />
        )}
      </>
    );
  }

  function renderMoreFields(idPrefix: string): ReactNode {
    return (
      <div className="flex flex-col gap-4">
        <MultiSelectPopover
          id={`${idPrefix}-categories`}
          label="Category"
          options={(options?.categories ?? []).map((category) => ({ value: category, label: category }))}
          selected={filters.categories}
          onChange={(values) => patchFilters({ categories: values })}
        />

        <MultiSelectPopover
          id={`${idPrefix}-accounts`}
          label="Account"
          options={(options?.accounts ?? []).map((account) => ({ value: account, label: account }))}
          selected={filters.accounts}
          onChange={(values) => patchFilters({ accounts: values })}
        />

        <div className="grid grid-cols-2 gap-2">
          <div className={fieldClass}>
            <label htmlFor={`${idPrefix}-amount-min`} className={labelClass}>
              Min amount
            </label>
            <input
              id={`${idPrefix}-amount-min`}
              type="number"
              inputMode="decimal"
              value={filters.amount_min ?? ''}
              onChange={(event) =>
                patchFilters({ amount_min: event.target.value === '' ? null : Number(event.target.value) })
              }
              className={selectClass}
            />
          </div>
          <div className={fieldClass}>
            <label htmlFor={`${idPrefix}-amount-max`} className={labelClass}>
              Max amount
            </label>
            <input
              id={`${idPrefix}-amount-max`}
              type="number"
              inputMode="decimal"
              value={filters.amount_max ?? ''}
              onChange={(event) =>
                patchFilters({ amount_max: event.target.value === '' ? null : Number(event.target.value) })
              }
              className={selectClass}
            />
          </div>
        </div>

        <div className={fieldClass}>
          <label htmlFor={`${idPrefix}-search`} className={labelClass}>
            Description search
          </label>
          <input
            id={`${idPrefix}-search`}
            type="search"
            value={searchDraft}
            onChange={(event) => setSearchDraft(event.target.value)}
            className={selectClass}
          />
        </div>

        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            checked={filters.outliers_only}
            onChange={(event) => patchFilters({ outliers_only: event.target.checked })}
            className="h-4 w-4"
          />
          Flagged only
        </label>

        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            checked={filters.duplicates_only}
            onChange={(event) => patchFilters({ duplicates_only: event.target.checked })}
            className="h-4 w-4"
          />
          Possible duplicates only
        </label>
      </div>
    );
  }

  return (
    <div className="sticky top-0 z-40 border-b border-hairline bg-surface-1 px-3 py-3 sm:px-6">
      {/* Desktop / tablet layout */}
      <div className="hidden flex-wrap items-end gap-3 sm:flex">
        {renderCoreControls('desktop')}

        <div className="relative">
          <button
            ref={moreButtonRef}
            type="button"
            aria-expanded={morePopoverOpen}
            aria-haspopup="dialog"
            onClick={() => setMorePopoverOpen((open) => !open)}
            className="min-h-9 rounded-md border border-hairline bg-surface-1 px-3 py-1 text-sm font-medium text-ink hover:bg-surface-2"
          >
            More filters
          </button>
          {morePopoverOpen && (
            <div
              role="dialog"
              aria-label="More filters"
              className="absolute left-0 z-20 mt-2 w-80 rounded-md border border-hairline bg-surface-1 p-4 shadow-lg"
            >
              {renderMoreFields('desktop-more')}
            </div>
          )}
        </div>

        {activeCount > 0 && (
          <button
            type="button"
            onClick={reset}
            className="min-h-9 rounded-md px-3 py-1 text-sm font-medium text-neutral-text hover:bg-surface-2"
          >
            Clear all
          </button>
        )}
      </div>

      {/* Mobile layout */}
      <div className="sm:hidden">
        <button
          type="button"
          aria-expanded={mobileSheetOpen}
          aria-haspopup="dialog"
          onClick={() => setMobileSheetOpen(true)}
          className="min-h-9 rounded-md border border-hairline bg-surface-1 px-3 py-2 text-sm font-medium text-ink"
        >
          Filters{activeCount > 0 ? ` (${activeCount})` : ''}
        </button>

        {mobileSheetOpen && (
          <div
            className="fixed inset-0 z-30 flex flex-col justify-end bg-black/40"
            onClick={() => setMobileSheetOpen(false)}
          >
            <div
              role="dialog"
              aria-label="Filters"
              onClick={(event) => event.stopPropagation()}
              className="max-h-[85vh] overflow-y-auto rounded-t-xl border-t border-hairline bg-surface-1 p-4"
            >
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-base font-semibold text-ink">Filters</h2>
                <button
                  type="button"
                  onClick={() => setMobileSheetOpen(false)}
                  aria-label="Close filters"
                  className="min-h-9 rounded-md px-2 text-sm font-medium text-ink-secondary hover:text-ink"
                >
                  Close
                </button>
              </div>
              <div className="flex flex-col gap-4">
                {renderCoreControls('mobile')}
                {renderMoreFields('mobile')}
              </div>
              {activeCount > 0 && (
                <button
                  type="button"
                  onClick={reset}
                  className="mt-4 min-h-9 w-full rounded-md border border-hairline px-3 py-2 text-sm font-medium text-ink"
                >
                  Clear all
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Active-filter chips */}
      {chips.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {chips.map((chip) => (
            <button
              key={chip.id}
              type="button"
              onClick={() => setFilters(chip.remove(filters))}
              className="flex items-center gap-1 rounded-full border border-hairline bg-surface-2 px-2 py-1 text-xs font-medium text-ink hover:bg-surface-3"
            >
              {chip.label}
              <span aria-hidden="true">×</span>
              <span className="sr-only">Remove filter: {chip.label}</span>
            </button>
          ))}
          <button
            type="button"
            onClick={reset}
            className="text-xs font-medium text-ink-secondary underline hover:text-ink"
          >
            Clear all
          </button>
        </div>
      )}
    </div>
  );
}
