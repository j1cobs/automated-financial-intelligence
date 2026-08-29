/**
 * The filter -> URL -> refetch seam (PLAN.md Phase 15, Fix 9).
 *
 * `filters.test.ts` covers serialization and `FilterBar.test.tsx` covers the controls,
 * but neither exercises the wiring between them: that a filter change produces a
 * genuinely different cache entry AND a request carrying the new params. That wiring is
 * the whole point of the change, and it fails silently — a constant query key still
 * renders, it just renders stale, differently-filtered numbers. Hence this file.
 *
 * The prefix-match test matters just as much: `mutations.ts` invalidates with the BASE
 * key (`['ledger']`), relying on TanStack's default prefix matching to reach every
 * `['ledger', filters]` variant. If those base keys ever stop being a prefix of the full
 * keys, editing a transaction stops refreshing the dashboard and nothing else complains.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React, { type ReactNode } from 'react';

vi.mock('./api', () => ({
  apiFetch: vi.fn(() => Promise.resolve({ ok: true })),
}));

import { apiFetch } from './api';
import { FilterProvider, useFilters } from './FilterContext';
import { useOverview, useLedger, ledgerQueryKey } from './queries';
import { DEFAULT_FILTERS } from './filters';

const mockedApiFetch = vi.mocked(apiFetch);

function makeClient({ staleTime = 0 }: { staleTime?: number } = {}) {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity, staleTime } },
  });
}

function wrapperFor(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client },
      React.createElement(FilterProvider, null, children),
    );
  };
}

/** Paths passed to apiFetch, in call order. */
function requestedPaths(): string[] {
  return mockedApiFetch.mock.calls.map((call) => String(call[0]));
}

beforeEach(() => {
  mockedApiFetch.mockClear();
  window.history.replaceState({}, '', '/');
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('filter-aware query hooks', () => {
  it('omits the query string entirely when every filter is at its default', async () => {
    const client = makeClient();
    renderHook(() => useOverview(), { wrapper: wrapperFor(client) });

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalled());
    expect(requestedPaths()[0]).toBe('/overview');
  });

  it('sends the active filters as query params', async () => {
    const client = makeClient();
    const { result } = renderHook(() => ({ overview: useOverview(), filterState: useFilters() }), {
      wrapper: wrapperFor(client),
    });

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalled());

    act(() => {
      result.current.filterState.patchFilters({ owners: ['Jacob'], period: 'all_time' });
    });

    await waitFor(() => expect(mockedApiFetch.mock.calls.length).toBeGreaterThan(1));
    const latest = requestedPaths().at(-1)!;
    expect(latest).toContain('owners=Jacob');
    expect(latest).toContain('period=all_time');
  });

  it('refetches when a filter changes rather than serving the previous result', async () => {
    const client = makeClient();
    const { result } = renderHook(() => ({ overview: useOverview(), filterState: useFilters() }), {
      wrapper: wrapperFor(client),
    });

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(1));

    act(() => {
      result.current.filterState.patchFilters({ categories: ['Groceries'] });
    });

    // A constant query key would leave this at 1 and quietly show unfiltered data.
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(2));
  });

  it('caches each filter set separately and reuses it on return', async () => {
    // `staleTime: Infinity` isolates the property under test. With the app's default
    // staleTime of 0, returning to a cached filter set serves the cached data AND fires
    // a background revalidation — correct behaviour, but it masks whether the two filter
    // sets got distinct cache entries in the first place, which is what this asserts.
    const client = makeClient({ staleTime: Infinity });
    const { result } = renderHook(() => ({ overview: useOverview(), filterState: useFilters() }), {
      wrapper: wrapperFor(client),
    });

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(1));

    act(() => {
      result.current.filterState.patchFilters({ period: 'all_time' });
    });
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(2));

    act(() => {
      result.current.filterState.setFilters(DEFAULT_FILTERS);
    });

    // Back to a filter set already in cache — served from it, no third request.
    await waitFor(() => expect(result.current.overview.data).toBeDefined());
    expect(mockedApiFetch).toHaveBeenCalledTimes(2);
  });
});

describe('base query keys stay prefix-compatible with mutations', () => {
  it('invalidating the base key reaches a filtered cache entry', async () => {
    const client = makeClient();
    const { result } = renderHook(() => ({ ledger: useLedger(), filterState: useFilters() }), {
      wrapper: wrapperFor(client),
    });

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(1));

    act(() => {
      result.current.filterState.patchFilters({ owners: ['Alexie'] });
    });
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(2));

    // Exactly what mutations.ts does after a ledger edit.
    await act(async () => {
      await client.invalidateQueries({ queryKey: ledgerQueryKey });
    });

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(3));
  });
});
