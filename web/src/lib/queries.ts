/**
 * TanStack Query hooks for the dashboard GET endpoints, each a thin wrapper
 * around `apiFetch` (which handles the cross-origin cookie + CSRF concerns —
 * see `lib/api.ts`). One hook per endpoint, typed against `lib/types.ts`.
 *
 * Every filtered hook reads the current `DashboardFilters` from
 * `FilterContext` itself — callers don't pass filters in, so
 * `OverviewTab`/`CashFlowTab`/`BudgetTab`/`TransactionsTab` need no changes
 * to become filter-aware; they just need to render under `<FilterProvider>`
 * (see `dashboard/Dashboard.tsx`).
 *
 * Query keys append the filters object (`['overview', filters]`, not just
 * `['overview']`) so a filter change is a genuinely different cache entry —
 * a constant key would serve stale, differently-filtered data straight out
 * of cache. The base keys below (`overviewQueryKey` etc) stay plain arrays
 * so `lib/mutations.ts`'s `invalidateQueries({ queryKey: overviewQueryKey })`
 * keeps matching every filter variant via TanStack's default prefix match.
 */

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from './api';
import { useFilters } from './FilterContext';
import { toSearchParams, type DashboardFilters } from './filters';
import type {
  OverviewResponse,
  HomeResponse,
  CashFlowResponse,
  BudgetResponse,
  LedgerResponse,
  AnomaliesResponse,
  CategoriesResponse,
  FilterOptions,
} from './types';

export const overviewQueryKey = ['overview'] as const;
export const homeQueryKey = ['home'] as const;
export const cashFlowQueryKey = ['cash-flow'] as const;
export const budgetQueryKey = ['budget'] as const;
export const ledgerQueryKey = ['ledger'] as const;
export const anomaliesQueryKey = ['anomalies'] as const;
export const categoriesQueryKey = ['categories'] as const;
export const filterOptionsQueryKey = ['filter-options'] as const;

/** Append the filters' query string to a path; omits `?` entirely when every filter is default. */
function withFilters(path: string, filters: DashboardFilters): string {
  const qs = toSearchParams(filters).toString();
  return qs ? `${path}?${qs}` : path;
}

export function useOverview() {
  const { filters } = useFilters();
  return useQuery({
    queryKey: [...overviewQueryKey, filters],
    queryFn: () => apiFetch<OverviewResponse>(withFilters('/overview', filters)),
  });
}

// Filter-aware: `/home` applies every filter except period (see api/filters.py's
// `apply_filters`, `all_time`) -- Home is a status page, not a period-scoped view.
export function useHome() {
  const { filters } = useFilters();
  return useQuery({
    queryKey: [...homeQueryKey, filters],
    queryFn: () => apiFetch<HomeResponse>(withFilters('/home', filters)),
  });
}

export function useCashFlow() {
  const { filters } = useFilters();
  return useQuery({
    queryKey: [...cashFlowQueryKey, filters],
    queryFn: () => apiFetch<CashFlowResponse>(withFilters('/cash-flow', filters)),
  });
}

export function useBudget() {
  const { filters } = useFilters();
  return useQuery({
    queryKey: [...budgetQueryKey, filters],
    queryFn: () => apiFetch<BudgetResponse>(withFilters('/budget', filters)),
  });
}

export function useLedger() {
  const { filters } = useFilters();
  return useQuery({
    queryKey: [...ledgerQueryKey, filters],
    queryFn: () => apiFetch<LedgerResponse>(withFilters('/ledger', filters)),
  });
}

export function useAnomalies() {
  const { filters } = useFilters();
  return useQuery({
    queryKey: [...anomaliesQueryKey, filters],
    queryFn: () => apiFetch<AnomaliesResponse>(withFilters('/anomalies', filters)),
  });
}

// Not filter-aware: GET /categories takes no filter params (api/routers/data.py).
export function useCategories() {
  return useQuery({
    queryKey: categoriesQueryKey,
    queryFn: () => apiFetch<CategoriesResponse>('/categories'),
  });
}

// Not filter-aware: options are always derived from the UNFILTERED frame
// (api/routers/data.py::get_filter_options) so the lists don't shrink out
// from under the user as they narrow the view.
export function useFilterOptions() {
  return useQuery({
    queryKey: filterOptionsQueryKey,
    queryFn: () => apiFetch<FilterOptions>('/filter-options'),
  });
}
