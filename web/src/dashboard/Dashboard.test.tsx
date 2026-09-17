import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { UseQueryResult } from '@tanstack/react-query';
import { Dashboard } from './Dashboard';
import type {
  OverviewResponse,
  CashFlowResponse,
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

const overviewData: OverviewResponse = {
  net_worth: {
    net_worth: 100000,
    total_assets: 120000,
    total_liabilities: 20000,
    asset_mix: [],
    owner_balances: [],
    credit_utilization: [],
    stale_accounts: [],
    dormant_accounts: [],
    forked_accounts: [],
  },
  overview: {
    income: 5000,
    expenses: 3000,
    net_flow: 2000,
    savings_rate: 0.4,
    flagged_count: 0,
    avg_weekly_expense: 750,
    avg_monthly_expense: 3000,
    avg_weekly_income: 1250,
    avg_monthly_income: 5000,
    avg_monthly_net: 2000,
    complete_months: 3,
    metrics: {
      net_worth: {
        key: 'net_worth',
        value: 100000,
        baseline: 95000,
        delta_pct: 0.0526,
        baseline_months: 0,
        sparkline: [],
        comparison_kind: 'last_period',
      },
      total_assets: {
        key: 'total_assets',
        value: 120000,
        baseline: 115000,
        delta_pct: 0.0435,
        baseline_months: 0,
        sparkline: [],
        comparison_kind: 'last_period',
      },
      total_liabilities: {
        key: 'total_liabilities',
        value: 20000,
        baseline: 20000,
        delta_pct: 0,
        baseline_months: 0,
        sparkline: [],
        comparison_kind: 'last_period',
      },
      avg_weekly_income: {
        key: 'avg_weekly_income',
        value: 1250,
        baseline: 1200,
        delta_pct: 0.0417,
        baseline_months: 3,
        sparkline: [1100, 1200, 1250],
        comparison_kind: 'trailing_average',
      },
      avg_weekly_expense: {
        key: 'avg_weekly_expense',
        value: 750,
        baseline: 720,
        delta_pct: 0.0417,
        baseline_months: 3,
        sparkline: [700, 710, 750],
        comparison_kind: 'trailing_average',
      },
      avg_monthly_income: {
        key: 'avg_monthly_income',
        value: 5000,
        baseline: 4800,
        delta_pct: 0.0417,
        baseline_months: 3,
        sparkline: [4600, 4800, 5000],
        comparison_kind: 'trailing_average',
      },
      avg_monthly_expense: {
        key: 'avg_monthly_expense',
        value: 3000,
        baseline: 2900,
        delta_pct: 0.0345,
        baseline_months: 3,
        sparkline: [2800, 2900, 3000],
        comparison_kind: 'trailing_average',
      },
      avg_monthly_net: {
        key: 'avg_monthly_net',
        value: 2000,
        baseline: 1900,
        delta_pct: 0.0526,
        baseline_months: 3,
        sparkline: [1800, 1900, 2000],
        comparison_kind: 'trailing_average',
      },
      savings_rate: {
        key: 'savings_rate',
        value: 0.4,
        baseline: null,
        delta_pct: null,
        baseline_months: 0,
        sparkline: [],
        comparison_kind: 'trailing_average',
      },
    },
    top_categories: [],
    month_over_month: [],
    emergency_fund_months: 3,
    income_breakdown: [],
    savings_rate_trend: [],
    net_worth_trend_daily: [],
    net_worth_trend_monthly: [],
    net_worth_mom_delta: null,
    recurring_items: [],
    top_merchants: [],
    cash_flow_projection: null,
    biggest_expense_this_month: null,
    upcoming_recurring: [],
  },
};

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
  vi.mocked(queries.useOverview).mockReturnValue(successResult<OverviewResponse>(overviewData));
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
