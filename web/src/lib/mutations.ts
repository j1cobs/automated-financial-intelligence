/**
 * TanStack Query mutation hooks for the 5 write endpoints. Each wraps
 * `apiFetch` (which attaches the CSRF header on non-GET requests — see
 * `lib/api.ts`) and invalidates the query/queries whose data the write
 * affects, so the UI reflects the change without a manual refetch.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from './api';
import {
  overviewQueryKey,
  cashFlowQueryKey,
  budgetQueryKey,
  ledgerQueryKey,
  anomaliesQueryKey,
} from './queries';

export function useSetCreditLimit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ accountKey, limit }: { accountKey: string; limit: number | null }) =>
      apiFetch<void>(`/accounts/${encodeURIComponent(accountKey)}/credit-limit`, {
        method: 'PATCH',
        body: { limit },
      }),
    onSuccess: () => {
      // Credit utilization/net worth is part of the overview view model.
      void queryClient.invalidateQueries({ queryKey: overviewQueryKey });
    },
  });
}

export function useUpsertBudget() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ category, monthlyLimit }: { category: string; monthlyLimit: number }) =>
      apiFetch<void>(`/budgets/${encodeURIComponent(category)}`, {
        method: 'PUT',
        body: { monthly_limit: monthlyLimit },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: budgetQueryKey });
    },
  });
}

export function useUpdateCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ hash, category }: { hash: string; category: string }) =>
      apiFetch<void>(`/transactions/${encodeURIComponent(hash)}/category`, {
        method: 'PATCH',
        body: { category },
      }),
    onSuccess: () => {
      // Category edits ripple into the ledger row itself and every
      // category-bucketed view (overview top categories, cash-flow
      // distribution, budget spend-per-category, anomalies list).
      void queryClient.invalidateQueries({ queryKey: ledgerQueryKey });
      void queryClient.invalidateQueries({ queryKey: overviewQueryKey });
      void queryClient.invalidateQueries({ queryKey: cashFlowQueryKey });
      void queryClient.invalidateQueries({ queryKey: budgetQueryKey });
      void queryClient.invalidateQueries({ queryKey: anomaliesQueryKey });
    },
  });
}

export function useUpdateRecurring() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ hash, recurring }: { hash: string; recurring: boolean }) =>
      apiFetch<void>(`/transactions/${encodeURIComponent(hash)}/recurring`, {
        method: 'PATCH',
        body: { recurring },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ledgerQueryKey });
    },
  });
}

export function useUpdateDuplicate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ hash, duplicate }: { hash: string; duplicate: boolean }) =>
      apiFetch<void>(`/transactions/${encodeURIComponent(hash)}/duplicate`, {
        method: 'PATCH',
        body: { duplicate },
      }),
    onSuccess: () => {
      // is_duplicate changes which rows are excluded everywhere except the
      // ledger (see api/viewmodels.py's exclude_duplicate_rows), so every
      // other read is potentially stale too.
      void queryClient.invalidateQueries({ queryKey: ledgerQueryKey });
      void queryClient.invalidateQueries({ queryKey: overviewQueryKey });
      void queryClient.invalidateQueries({ queryKey: cashFlowQueryKey });
      void queryClient.invalidateQueries({ queryKey: budgetQueryKey });
      void queryClient.invalidateQueries({ queryKey: anomaliesQueryKey });
    },
  });
}
