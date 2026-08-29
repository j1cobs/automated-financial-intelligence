import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { UseQueryResult } from '@tanstack/react-query';
import { Dashboard } from './Dashboard';
import type {
  CashFlowResponse,
  HomeResponse,
  LedgerResponse,
  AnomaliesResponse,
  CategoriesResponse,
  FilterOptions,
} from '../lib/types';

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({
    user: { email: 'test@example.com', name: null, picture: null },
    csrfToken: null,
    isLoading: false,
    isAuthenticated: true,
  }),
}));

// Same rationale as CashFlowTab.test.tsx: jsdom has no ResizeObserver, so
// Recharts' ResponsiveContainer never sees a nonzero size without this.
vi.mock('recharts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('recharts')>();
  return {
    ...actual,
    ResponsiveContainer: ({
      children,
    }: {
      children: React.ReactElement<{ width?: number; height?: number }>;
    }) => React.cloneElement(children, { width: 800, height: 400 }),
  };
});

vi.mock('../lib/queries');
import * as queries from '../lib/queries';

function loadingResult<T>(): UseQueryResult<T, Error> {
  return {
    data: undefined,
    status: 'pending',
    isLoading: true,
    isError: false,
    error: null,
    fetchStatus: 'fetching',
    isPending: true,
    isSuccess: false,
    isFetching: true,
    isStale: false,
    isPlaceholderData: false,
    failureCount: 0,
    failureReason: null,
    refetch: vi.fn(),
    remove: vi.fn(),
    dataUpdatedAt: 0,
    errorUpdatedAt: 0,
  } as unknown as UseQueryResult<T, Error>;
}

function successResult<T>(data: T): UseQueryResult<T, Error> {
  return {
    data,
    status: 'success',
    isLoading: false,
    isError: false,
    error: null,
    fetchStatus: 'idle',
    isPending: false,
    isSuccess: true,
    isFetching: false,
    isStale: false,
    isPlaceholderData: false,
    failureCount: 0,
    failureReason: null,
    refetch: vi.fn(),
    remove: vi.fn(),
    dataUpdatedAt: Date.now(),
    errorUpdatedAt: 0,
  } as unknown as UseQueryResult<T, Error>;
}

const cashFlowData: CashFlowResponse = {
  income: 5000,
  expenses: 3000,
  net_flow: 2000,
  transfer_count: 0,
  flagged_count: 0,
  savings_rate: 0.4,
  month_over_month: [],
  weekly_trend: [],
  rolling_30d_spend: [
    { date: '2024-02-01', amount: 3000, daily_avg: 100 },
    { date: '2024-02-02', amount: 3100, daily_avg: 103.3 },
  ],
  monthly_net_by_owner: [],
  category_distribution: [],
};

function setupQueryMocks() {
  vi.mocked(queries.useHome).mockReturnValue(loadingResult<HomeResponse>());
  vi.mocked(queries.useCashFlow).mockReturnValue(successResult<CashFlowResponse>(cashFlowData));
  vi.mocked(queries.useLedger).mockReturnValue(loadingResult<LedgerResponse>());
  vi.mocked(queries.useAnomalies).mockReturnValue(loadingResult<AnomaliesResponse>());
  vi.mocked(queries.useCategories).mockReturnValue(loadingResult<CategoriesResponse>());
  vi.mocked(queries.useFilterOptions).mockReturnValue(loadingResult<FilterOptions>());
}

function renderDashboard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <Dashboard />
    </QueryClientProvider>,
  );
}

describe('Dashboard cross-tab drill-down (rolling 30-day spend -> Transactions)', () => {
  beforeEach(() => {
    // Non-default filters active *before* the drill-down, so the "Back"
    // assertion below can catch a "silently resets to DEFAULT_FILTERS
    // instead of restoring" bug -- a bug that a default-filters starting
    // point could never expose.
    window.history.replaceState(null, '', '/?owners=Alice');
    setupQueryMocks();
  });

  afterEach(() => {
    window.history.replaceState(null, '', '/');
  });

  it('switches to Transactions with the correct 30-day filter range, and Back restores the exact prior filters + tab', () => {
    renderDashboard();

    fireEvent.click(screen.getByRole('button', { name: 'Cash Flow' }));
    expect(screen.getByText('Rolling 30-day spend')).toBeInTheDocument();

    const chart = screen.getByTestId('rolling-spend-chart');
    const point = chart.querySelector('[data-testid="rolling-spend-point-0"]');
    expect(point).toBeTruthy();
    fireEvent.click(point!);

    // Landed on Transactions (the "Back to Cash Flow" button only renders there).
    expect(screen.getByRole('button', { name: /back to cash flow/i })).toBeInTheDocument();

    // date-2024-02-01's 30-day window is [2024-01-03, 2024-02-01].
    const params = new URLSearchParams(window.location.search);
    expect(params.get('period')).toBe('custom');
    expect(params.get('date_from')).toBe('2024-01-03');
    expect(params.get('date_to')).toBe('2024-02-01');
    // Narrowing preserved the filters that were already active.
    expect(params.getAll('owners')).toEqual(['Alice']);

    fireEvent.click(screen.getByRole('button', { name: /back to cash flow/i }));

    // Restored to the *exact* pre-drill-down filters (owners kept, the
    // drill-down's date/period narrowing gone) -- not DEFAULT_FILTERS, which
    // would also have dropped `owners=Alice`.
    const restoredParams = new URLSearchParams(window.location.search);
    expect(restoredParams.getAll('owners')).toEqual(['Alice']);
    expect(restoredParams.get('date_from')).toBeNull();
    expect(restoredParams.get('period')).toBeNull();
    expect(screen.getByRole('heading', { name: 'Cash Flow' })).toBeInTheDocument();
  });
});
