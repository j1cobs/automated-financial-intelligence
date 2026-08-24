/**
 * Filter state for the dashboard, synced to the URL via `history.replaceState`
 * — deliberately no router dependency, mirroring the tab-switching decision in
 * `dashboard/Dashboard.tsx` (local `useState`, no router). Initialising from
 * `window.location.search` on mount is what makes a pasted/bookmarked URL
 * reproduce the same filtered view.
 *
 * `replaceState`, not `pushState`: every filter tweak is a variation on "the
 * dashboard", not a new place to visit — back/forward shouldn't have to click
 * through every keystroke of a search box.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { DEFAULT_FILTERS, fromSearchParams, toSearchParams, type DashboardFilters } from './filters';

interface FilterContextValue {
  filters: DashboardFilters;
  setFilters: (filters: DashboardFilters) => void;
  /** Merge a partial update into the current filters. */
  patchFilters: (patch: Partial<DashboardFilters>) => void;
  reset: () => void;
}

const FilterContext = createContext<FilterContextValue | undefined>(undefined);

function readInitialFilters(): DashboardFilters {
  if (typeof window === 'undefined') return DEFAULT_FILTERS;
  try {
    return fromSearchParams(new URLSearchParams(window.location.search));
  } catch {
    return DEFAULT_FILTERS;
  }
}

export function FilterProvider({ children }: { children: ReactNode }) {
  const [filters, setFiltersState] = useState<DashboardFilters>(readInitialFilters);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const qs = toSearchParams(filters).toString();
    const url = `${window.location.pathname}${qs ? `?${qs}` : ''}${window.location.hash}`;
    window.history.replaceState(window.history.state, '', url);
  }, [filters]);

  const setFilters = useCallback((next: DashboardFilters) => setFiltersState(next), []);

  const patchFilters = useCallback(
    (patch: Partial<DashboardFilters>) => setFiltersState((prev) => ({ ...prev, ...patch })),
    [],
  );

  const reset = useCallback(() => setFiltersState(DEFAULT_FILTERS), []);

  const value = useMemo(
    () => ({ filters, setFilters, patchFilters, reset }),
    [filters, setFilters, patchFilters, reset],
  );

  return <FilterContext.Provider value={value}>{children}</FilterContext.Provider>;
}

// Same shape as `AuthContext.tsx`'s `useAuth` export: a hook living alongside
// its provider in one file trips react-refresh's "only export components"
// rule. AuthContext.tsx accepts that warning; this file suppresses it instead
// so the lint warning count doesn't grow past what AuthContext already carries.
// eslint-disable-next-line react-refresh/only-export-components
export function useFilters(): FilterContextValue {
  const context = useContext(FilterContext);
  if (!context) {
    throw new Error('useFilters must be used within a FilterProvider');
  }
  return context;
}
