/**
 * Replaces native `<select multiple>` (FilterBar's original owner/month/
 * category/account controls) with a button that opens a checkbox popover:
 * search field, select-all/clear, and a scrollable checkbox list. Native
 * multi-selects require ctrl+click, are effectively broken on touch, and
 * are close to unstylable — this is the conventional, accessible, touch-
 * friendly replacement. Purely a control; the filter *state* it reads and
 * writes is still `DashboardFilters['owners' | 'months' | ...]` via the
 * `selected`/`onChange` props, so `lib/filters.ts` / `FilterContext.tsx`
 * are untouched.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

export interface MultiSelectOption {
  value: string;
  label: string;
}

interface MultiSelectPopoverProps {
  id: string;
  label: string;
  options: MultiSelectOption[];
  selected: string[] | null;
  onChange: (values: string[] | null) => void;
  className?: string;
}

// Below this many options, a search field is more friction than it saves.
const SEARCH_THRESHOLD = 6;

export function MultiSelectPopover({
  id,
  label,
  options,
  selected,
  onChange,
  className,
}: MultiSelectPopoverProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const selectedValues = selected ?? [];

  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter((option) => option.label.toLowerCase().includes(q));
  }, [options, query]);

  function toggleValue(value: string) {
    const next = selectedValues.includes(value)
      ? selectedValues.filter((entry) => entry !== value)
      : [...selectedValues, value];
    onChange(next.length > 0 ? next : null);
  }

  function selectAllFiltered() {
    if (filtered.length === 0) return;
    const merged = new Set([...selectedValues, ...filtered.map((option) => option.value)]);
    onChange(Array.from(merged));
  }

  function clearAll() {
    onChange(null);
  }

  const buttonLabel = selectedValues.length > 0 ? `${label} (${selectedValues.length})` : label;

  return (
    <div className={`relative flex flex-col gap-1 ${className ?? ''}`} ref={containerRef}>
      {/* Not a `<label for>`: that would make the browser use this static text
          as the button's accessible name, silently dropping the "(N)" count
          from what a screen reader announces. `aria-label` on the button
          carries the real (dynamic) name instead; this is purely visual. */}
      <span id={`${id}-caption`} className="text-xs font-medium text-ink-secondary" aria-hidden="true">
        {label}
      </span>
      <button
        id={id}
        ref={triggerRef}
        type="button"
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={buttonLabel}
        onClick={() =>
          setOpen((wasOpen) => {
            if (!wasOpen) setQuery('');
            return !wasOpen;
          })
        }
        className="min-h-9 rounded-md border border-hairline bg-surface-1 px-2 py-1 text-left text-sm text-ink focus:outline-none focus:ring-2 focus:ring-cat-1"
      >
        {buttonLabel}
      </button>
      {open && (
        <div
          role="dialog"
          aria-label={label}
          className="absolute left-0 top-full z-20 mt-1 w-64 rounded-md border border-hairline bg-surface-1 p-2 shadow-lg"
        >
          {options.length > SEARCH_THRESHOLD && (
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={`Search ${label.toLowerCase()}...`}
              aria-label={`Search ${label.toLowerCase()}`}
              className="mb-2 w-full min-h-8 rounded-md border border-hairline bg-surface-1 px-2 py-1 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-cat-1"
            />
          )}
          <div className="mb-2 flex items-center gap-2 text-xs font-medium text-ink-secondary">
            <button
              type="button"
              onClick={selectAllFiltered}
              disabled={filtered.length === 0}
              className="hover:text-ink disabled:opacity-50"
            >
              Select all
            </button>
            <span aria-hidden="true">·</span>
            <button
              type="button"
              onClick={clearAll}
              disabled={selectedValues.length === 0}
              className="hover:text-ink disabled:opacity-50"
            >
              Clear
            </button>
          </div>
          <div className="max-h-56 overflow-y-auto">
            {filtered.length === 0 && <p className="px-1 py-2 text-sm text-ink-muted">No matches</p>}
            {filtered.map((option) => (
              <label
                key={option.value}
                className="flex min-h-8 items-center gap-2 rounded px-1 text-sm text-ink hover:bg-surface-2"
              >
                <input
                  type="checkbox"
                  checked={selectedValues.includes(option.value)}
                  onChange={() => toggleValue(option.value)}
                  className="h-4 w-4"
                />
                {option.label}
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
