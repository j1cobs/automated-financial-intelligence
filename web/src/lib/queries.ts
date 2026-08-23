/**
 * TanStack Query hooks for the 6 GET dashboard endpoints, each a thin wrapper
 * around `apiFetch` (which handles the cross-origin cookie + CSRF concerns —
 * see `lib/api.ts`). One hook per endpoint, typed against `lib/types.ts`.
 */

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from './api';
import type {
  OverviewResponse,
  CashFlowResponse,
  BudgetResponse,
  LedgerResponse,
  AnomaliesResponse,
  CategoriesResponse,
} from './types';

export const overviewQueryKey = ['overview'] as const;
export const cashFlowQueryKey = ['cash-flow'] as const;
export const budgetQueryKey = ['budget'] as const;
export const ledgerQueryKey = ['ledger'] as const;
export const anomaliesQueryKey = ['anomalies'] as const;
export const categoriesQueryKey = ['categories'] as const;

export function useOverview() {
  return useQuery({
    queryKey: overviewQueryKey,
    queryFn: () => apiFetch<OverviewResponse>('/overview'),
  });
}

export function useCashFlow() {
  return useQuery({
    queryKey: cashFlowQueryKey,
    queryFn: () => apiFetch<CashFlowResponse>('/cash-flow'),
  });
}

export function useBudget() {
  return useQuery({
    queryKey: budgetQueryKey,
    queryFn: () => apiFetch<BudgetResponse>('/budget'),
  });
}

export function useLedger() {
  return useQuery({
    queryKey: ledgerQueryKey,
    queryFn: () => apiFetch<LedgerResponse>('/ledger'),
  });
}

export function useAnomalies() {
  return useQuery({
    queryKey: anomaliesQueryKey,
    queryFn: () => apiFetch<AnomaliesResponse>('/anomalies'),
  });
}

export function useCategories() {
  return useQuery({
    queryKey: categoriesQueryKey,
    queryFn: () => apiFetch<CategoriesResponse>('/categories'),
  });
}
