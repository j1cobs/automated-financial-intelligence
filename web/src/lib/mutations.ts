/**
 * TanStack Query mutation hooks for the 5 write endpoints.
 *
 * PLAN.md Phase 15, Fix 14: `useUpdateCategory`/`useUpdateRecurring`/`useUpdateDuplicate`
 * used to invalidate every query on success, so one inline ledger edit refetched all six
 * endpoints -- each of which re-reads and re-enriches the whole transaction table
 * server-side (`api/dataload.py`). They now:
 *
 *   1. Patch the ledger cache directly in `onMutate` (optimistic -- the row updates before
 *      the request resolves), snapshotting the previous data first.
 *   2. Restore that snapshot in `onError` -- the request's own `isError` is what the caller
 *      uses to surface the failure (see `TransactionsTab.tsx`'s inline banner).
 *   3. Refetch the ledger and, for `category`/`duplicate` only, debounce-invalidate the
 *      analytics endpoints in `onSettled` -- coalescing rapid successive edits (e.g.
 *      re-categorising several rows in a row) into one round of refetches instead of one
 *      per edit.
 *
 * `recurring` used to skip the analytics invalidation, on the grounds that no aggregate
 * read `is_recurring`. That stopped being true -- `build_overview` reads it for the
 * Committed/Recurring Spend card (`api/viewmodels.py:800`) -- so it now invalidates like
 * the others, or that card keeps showing a figure the toggle has already changed.
 *
 * Ledger cache surgery uses `queryClient.setQueriesData({ queryKey: ledgerQueryKey }, ...)`
 * rather than `setQueryData` with an exact key, for the same reason `invalidateQueries`
 * uses the base key elsewhere in this file: `useLedger()`'s real cache key is
 * `['ledger', filters]`, and TanStack's default matching for a bare `queryKey` is a
 * prefix match, not an exact one (see the comment block atop `queries.ts` and the
 * "base query keys stay prefix-compatible" test in `queries.test.ts`). An exact-key patch
 * would silently miss every filtered variant.
 */

import { useMutation, useQueryClient, type QueryClient, type QueryKey } from '@tanstack/react-query';
import { apiFetch } from './api';
import {
  overviewQueryKey,
  cashFlowQueryKey,
  budgetQueryKey,
  ledgerQueryKey,
  anomaliesQueryKey,
  goalsQueryKey,
} from './queries';
import type { CategoryUpdateResponse, LedgerItem, LedgerResponse } from './types';

/** Every analytics endpoint a ledger edit can change the numbers of. */
const ANALYTICS_QUERY_KEYS = [overviewQueryKey, cashFlowQueryKey, budgetQueryKey, anomaliesQueryKey] as const;

/** Coalescing window for the debounced analytics invalidation below. */
const ANALYTICS_INVALIDATE_DEBOUNCE_MS = 500;

/** One pending debounce timer per `QueryClient` -- tests each construct their own client,
 *  and a `WeakMap` keeps this module stateless across them without a manual reset. */
const pendingAnalyticsInvalidation = new WeakMap<QueryClient, ReturnType<typeof setTimeout>>();

/**
 * Invalidate every analytics endpoint, but not immediately: if another edit lands within
 * `ANALYTICS_INVALIDATE_DEBOUNCE_MS`, this timer is replaced rather than doubled up, so N
 * rapid edits produce one invalidation pass instead of N.
 */
function invalidateAnalyticsDebounced(queryClient: QueryClient): void {
  const existing = pendingAnalyticsInvalidation.get(queryClient);
  if (existing !== undefined) clearTimeout(existing);
  const timer = setTimeout(() => {
    pendingAnalyticsInvalidation.delete(queryClient);
    for (const key of ANALYTICS_QUERY_KEYS) {
      void queryClient.invalidateQueries({ queryKey: key });
    }
  }, ANALYTICS_INVALIDATE_DEBOUNCE_MS);
  pendingAnalyticsInvalidation.set(queryClient, timer);
}

type LedgerSnapshot = Array<[QueryKey, LedgerResponse | undefined]>;

/** Apply `patch` to the ledger row identified by `hash`, across every filtered ledger
 *  cache entry, and return the pre-patch snapshot for `restoreLedgerSnapshot`. */
function patchLedgerRow(
  queryClient: QueryClient,
  hash: string,
  patch: Partial<Pick<LedgerItem, 'category' | 'is_recurring' | 'is_duplicate' | 'linked_transaction_hash'>>,
): LedgerSnapshot {
  const snapshot = queryClient.getQueriesData<LedgerResponse>({ queryKey: ledgerQueryKey });
  queryClient.setQueriesData<LedgerResponse>({ queryKey: ledgerQueryKey }, (old) => {
    if (!old) return old;
    return {
      ...old,
      transactions: old.transactions.map((tx) => (tx.hash === hash ? { ...tx, ...patch } : tx)),
    };
  });
  return snapshot;
}

/** Undo `patchLedgerRow`, restoring exactly the data each cache entry held before. */
function restoreLedgerSnapshot(queryClient: QueryClient, snapshot: LedgerSnapshot): void {
  for (const [key, data] of snapshot) {
    queryClient.setQueryData(key, data);
  }
}

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
    mutationFn: ({
      category,
      monthlyLimit,
      month,
    }: {
      category: string;
      monthlyLimit: number;
      /** 'YYYY-MM'. Omitted means the current calendar month — never "all
       *  months", which is the flat-table behaviour Phase 28 replaced. The
       *  field is `month`, not `period`: the filter bar already owns `period`
       *  and its values are presets like 'all_time'. */
      month?: string;
    }) =>
      apiFetch<void>(`/budgets/${encodeURIComponent(category)}`, {
        method: 'PUT',
        body: month ? { monthly_limit: monthlyLimit, month } : { monthly_limit: monthlyLimit },
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
      apiFetch<CategoryUpdateResponse>(`/transactions/${encodeURIComponent(hash)}/category`, {
        method: 'PATCH',
        body: { category },
      }),
    onMutate: async ({ hash, category }) => {
      await queryClient.cancelQueries({ queryKey: ledgerQueryKey });
      const snapshot = patchLedgerRow(queryClient, hash, { category });
      return { snapshot };
    },
    onError: (_err, _vars, context) => {
      if (context) restoreLedgerSnapshot(queryClient, context.snapshot);
    },
    onSettled: () => {
      // Category edits ripple into every category-bucketed view (overview top
      // categories, cash-flow distribution, budget spend-per-category, anomalies
      // list) -- genuinely stale, so those still invalidate, just debounced.
      void queryClient.invalidateQueries({ queryKey: ledgerQueryKey });
      invalidateAnalyticsDebounced(queryClient);
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
    onMutate: async ({ hash, recurring }) => {
      await queryClient.cancelQueries({ queryKey: ledgerQueryKey });
      const snapshot = patchLedgerRow(queryClient, hash, { is_recurring: recurring });
      return { snapshot };
    },
    onError: (_err, _vars, context) => {
      if (context) restoreLedgerSnapshot(queryClient, context.snapshot);
    },
    onSettled: () => {
      // This used to skip analytics on the grounds that no aggregate read
      // `is_recurring`. That stopped being true: `build_overview` reads it for
      // the Committed/Recurring Spend card (api/viewmodels.py:800), which is
      // exactly the case the old comment warned about. Without this, toggling
      // Recurring left that card showing a figure that no longer matched.
      void queryClient.invalidateQueries({ queryKey: ledgerQueryKey });
      invalidateAnalyticsDebounced(queryClient);
    },
  });
}

/** Toggle recurring for a whole detected stream (Phase 31).
 *
 * The per-row mutation above still applies to transactions belonging to no
 * stream. This one exists because `is_recurring` is per-row: every occurrence
 * of the same charge was independently checkable, so the same bill could be
 * flagged over and over and Upcoming then listed near-duplicates.
 *
 * No optimistic patch here: one click changes an unknown number of rows, so
 * there is nothing honest to write into the cache up front. The ledger is
 * refetched instead. */
export function useUpdateStreamRecurring() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ streamId, recurring }: { streamId: string; recurring: boolean }) =>
      apiFetch<{ updated_count: number }>(`/streams/${encodeURIComponent(streamId)}/recurring`, {
        method: 'PATCH',
        body: { recurring },
      }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ledgerQueryKey });
      invalidateAnalyticsDebounced(queryClient);
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
    onMutate: async ({ hash, duplicate }) => {
      await queryClient.cancelQueries({ queryKey: ledgerQueryKey });
      const snapshot = patchLedgerRow(queryClient, hash, { is_duplicate: duplicate });
      return { snapshot };
    },
    onError: (_err, _vars, context) => {
      if (context) restoreLedgerSnapshot(queryClient, context.snapshot);
    },
    onSettled: () => {
      // is_duplicate changes which rows are excluded everywhere except the
      // ledger (see api/viewmodels.py's exclude_duplicate_rows), so every other
      // read is potentially stale too -- debounced along with category edits.
      void queryClient.invalidateQueries({ queryKey: ledgerQueryKey });
      invalidateAnalyticsDebounced(queryClient);
    },
  });
}

export function useLinkTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ hash, otherHash }: { hash: string; otherHash: string }) =>
      apiFetch<void>(`/transactions/${encodeURIComponent(hash)}/link`, {
        method: 'POST',
        body: { other_hash: otherHash },
      }),
    onMutate: async ({ hash, otherHash }) => {
      await queryClient.cancelQueries({ queryKey: ledgerQueryKey });
      const snapshot = patchLedgerRow(queryClient, hash, { linked_transaction_hash: otherHash });
      return { snapshot };
    },
    onError: (_err, _vars, context) => {
      if (context) restoreLedgerSnapshot(queryClient, context.snapshot);
    },
    onSettled: () => {
      // Linking changes which rows are netted into aggregates (linked pairs are
      // excluded from analytics), so every analytics read is potentially stale
      // too -- debounced along with category and duplicate edits.
      void queryClient.invalidateQueries({ queryKey: ledgerQueryKey });
      invalidateAnalyticsDebounced(queryClient);
    },
  });
}

export function useUnlinkTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (hash: string) =>
      apiFetch<void>(`/transactions/${encodeURIComponent(hash)}/link`, { method: 'DELETE' }),
    onMutate: async (hash) => {
      await queryClient.cancelQueries({ queryKey: ledgerQueryKey });
      const snapshot = patchLedgerRow(queryClient, hash, { linked_transaction_hash: null });
      return { snapshot };
    },
    onError: (_err, _vars, context) => {
      if (context) restoreLedgerSnapshot(queryClient, context.snapshot);
    },
    onSettled: () => {
      // Unlinking changes which rows are netted into aggregates, so every
      // analytics read is potentially stale too -- debounced along with category
      // and duplicate edits.
      void queryClient.invalidateQueries({ queryKey: ledgerQueryKey });
      invalidateAnalyticsDebounced(queryClient);
    },
  });
}

/** Dismiss one anomaly for one period (Phase 34).
 *
 * Period-scoped on purpose: dismissing September's Dining drift because of a
 * birthday must not silence October's. An alert that never comes back goes
 * quiet exactly as it becomes useful. */
export function useDismissAnomaly() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { kind: string; subject: string; period: string }) =>
      apiFetch<void>('/anomalies/dismiss', { method: 'POST', body }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: anomaliesQueryKey });
    },
  });
}

/** Fetch live balances on demand (Phase 35).
 *
 * Invalidates every analytics key rather than just one: a balance change moves
 * net worth, the emergency-fund figure and goal progress at once. */
export function useRefreshBalances() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<{ accounts_refreshed: number; accounts_failed: number }>('/accounts/refresh-balances', {
        method: 'POST',
      }),
    onSettled: () => {
      for (const key of ANALYTICS_QUERY_KEYS) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
    },
  });
}

/** Savings-goal writes (Phase 33). Each invalidates the goals list; goal
 *  numbers derive from account balances, which no goal write changes, so
 *  nothing else needs refetching. */
export function useCreateGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      name: string;
      target_amount: number;
      target_date: string | null;
      account_keys: string[];
    }) => apiFetch<unknown>('/goals', { method: 'POST', body }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: goalsQueryKey });
    },
  });
}

export function useDeleteGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (goalId: number) => apiFetch<void>(`/goals/${goalId}`, { method: 'DELETE' }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: goalsQueryKey });
    },
  });
}
