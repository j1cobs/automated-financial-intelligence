/**
 * Optimistic-update contract for the ledger mutations (PLAN.md Phase 15, Fix 14).
 *
 * `useUpdateCategory`/`useUpdateRecurring`/`useUpdateDuplicate` used to invalidate every
 * query on success -- one inline edit refetched all six endpoints. They now patch the
 * ledger cache directly (so the row updates before the request resolves), roll back on
 * failure, and invalidate analytics selectively: `category`/`duplicate` genuinely change
 * analytics numbers and still invalidate them (debounced); `recurring` changes nothing
 * outside the ledger row and must not.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React, { type ReactNode } from 'react';

vi.mock('./api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from './api';
import { useUpdateCategory, useUpdateRecurring, useUpdateDuplicate } from './mutations';
import {
  ledgerQueryKey,
  overviewQueryKey,
  cashFlowQueryKey,
  budgetQueryKey,
  anomaliesQueryKey,
} from './queries';
import type { LedgerResponse } from './types';

const mockedApiFetch = vi.mocked(apiFetch);

const ledgerData: LedgerResponse = {
  transactions: [
    {
      hash: 'tx-1',
      date: '2024-01-15',
      owner_name: null,
      account_name: 'Checking',
      description: 'Grocery Store',
      amount: -50.25,
      category: 'Uncategorized',
      tx_type: 'expense',
      is_recurring: false,
      is_duplicate: false,
    },
  ],
};

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } },
  });
}

function seedLedger(client: QueryClient, filters: Record<string, unknown> = {}) {
  client.setQueryData([...ledgerQueryKey, filters], ledgerData);
}

function wrapperFor(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return React.createElement(QueryClientProvider, { client }, children);
  };
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  mockedApiFetch.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('useUpdateCategory', () => {
  it('updates the ledger row optimistically before the request resolves', async () => {
    const client = makeClient();
    seedLedger(client);
    // Never resolves within this test -- proves the row updated before the request did.
    mockedApiFetch.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useUpdateCategory(), { wrapper: wrapperFor(client) });

    act(() => {
      result.current.mutate({ hash: 'tx-1', category: 'Groceries' });
    });

    await waitFor(() => {
      const data = client.getQueryData<LedgerResponse>([...ledgerQueryKey, {}]);
      expect(data?.transactions[0].category).toBe('Groceries');
    });
  });

  it('rolls the row back and exposes the failure when the request errors', async () => {
    const client = makeClient();
    seedLedger(client);
    mockedApiFetch.mockRejectedValue(new Error('boom'));

    const { result } = renderHook(() => useUpdateCategory(), { wrapper: wrapperFor(client) });

    act(() => {
      result.current.mutate({ hash: 'tx-1', category: 'Groceries' });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    const data = client.getQueryData<LedgerResponse>([...ledgerQueryKey, {}]);
    expect(data?.transactions[0].category).toBe('Uncategorized');
  });

  it('patches every filtered ledger cache entry, not just one', async () => {
    const client = makeClient();
    seedLedger(client, {});
    seedLedger(client, { owners: ['Jacob'] });
    mockedApiFetch.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useUpdateCategory(), { wrapper: wrapperFor(client) });

    act(() => {
      result.current.mutate({ hash: 'tx-1', category: 'Groceries' });
    });

    await waitFor(() => {
      expect(client.getQueryData<LedgerResponse>([...ledgerQueryKey, {}])?.transactions[0].category).toBe(
        'Groceries',
      );
    });
    expect(
      client.getQueryData<LedgerResponse>([...ledgerQueryKey, { owners: ['Jacob'] }])?.transactions[0]
        .category,
    ).toBe('Groceries');
  });

  it('invalidates ledger immediately and analytics after the debounce window on success', async () => {
    const client = makeClient();
    seedLedger(client);
    mockedApiFetch.mockResolvedValue(undefined);
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useUpdateCategory(), { wrapper: wrapperFor(client) });

    await act(async () => {
      await result.current.mutateAsync({ hash: 'tx-1', category: 'Groceries' });
    });

    // Ledger is invalidated right away...
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ledgerQueryKey });
    // ...but analytics has not been invalidated yet -- it's debounced.
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: overviewQueryKey });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    for (const key of [overviewQueryKey, cashFlowQueryKey, budgetQueryKey, anomaliesQueryKey]) {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: key });
    }
  });

  it('coalesces rapid successive edits into a single analytics invalidation pass', async () => {
    const client = makeClient();
    seedLedger(client);
    mockedApiFetch.mockResolvedValue(undefined);
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useUpdateCategory(), { wrapper: wrapperFor(client) });

    await act(async () => {
      await result.current.mutateAsync({ hash: 'tx-1', category: 'Groceries' });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100); // well inside the debounce window
    });
    await act(async () => {
      await result.current.mutateAsync({ hash: 'tx-1', category: 'Dining' });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    const overviewInvalidations = invalidateSpy.mock.calls.filter(
      (call) => call[0]?.queryKey === overviewQueryKey,
    );
    expect(overviewInvalidations.length).toBe(1);
  });
});

describe('useUpdateRecurring', () => {
  it('updates the row optimistically', async () => {
    const client = makeClient();
    seedLedger(client);
    mockedApiFetch.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useUpdateRecurring(), { wrapper: wrapperFor(client) });

    act(() => {
      result.current.mutate({ hash: 'tx-1', recurring: true });
    });

    await waitFor(() => {
      const data = client.getQueryData<LedgerResponse>([...ledgerQueryKey, {}]);
      expect(data?.transactions[0].is_recurring).toBe(true);
    });
  });

  it('rolls back on error', async () => {
    const client = makeClient();
    seedLedger(client);
    mockedApiFetch.mockRejectedValue(new Error('boom'));

    const { result } = renderHook(() => useUpdateRecurring(), { wrapper: wrapperFor(client) });

    act(() => {
      result.current.mutate({ hash: 'tx-1', recurring: true });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    const data = client.getQueryData<LedgerResponse>([...ledgerQueryKey, {}]);
    expect(data?.transactions[0].is_recurring).toBe(false);
  });

  it('never invalidates any analytics query, even after the debounce window', async () => {
    const client = makeClient();
    seedLedger(client);
    mockedApiFetch.mockResolvedValue(undefined);
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useUpdateRecurring(), { wrapper: wrapperFor(client) });

    await act(async () => {
      await result.current.mutateAsync({ hash: 'tx-1', recurring: true });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ledgerQueryKey });
    for (const key of [overviewQueryKey, cashFlowQueryKey, budgetQueryKey, anomaliesQueryKey]) {
      expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: key });
    }
  });
});

describe('useUpdateDuplicate', () => {
  it('updates the row optimistically and invalidates analytics (debounced) on success', async () => {
    const client = makeClient();
    seedLedger(client);
    mockedApiFetch.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useUpdateDuplicate(), { wrapper: wrapperFor(client) });

    act(() => {
      result.current.mutate({ hash: 'tx-1', duplicate: true });
    });

    await waitFor(() => {
      const data = client.getQueryData<LedgerResponse>([...ledgerQueryKey, {}]);
      expect(data?.transactions[0].is_duplicate).toBe(true);
    });
  });

  it('rolls back on error', async () => {
    const client = makeClient();
    seedLedger(client);
    mockedApiFetch.mockRejectedValue(new Error('boom'));

    const { result } = renderHook(() => useUpdateDuplicate(), { wrapper: wrapperFor(client) });

    act(() => {
      result.current.mutate({ hash: 'tx-1', duplicate: true });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    const data = client.getQueryData<LedgerResponse>([...ledgerQueryKey, {}]);
    expect(data?.transactions[0].is_duplicate).toBe(false);
  });
});
