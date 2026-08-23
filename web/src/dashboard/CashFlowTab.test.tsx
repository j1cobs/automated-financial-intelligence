import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { UseQueryResult } from '@tanstack/react-query';
import { CashFlowTab } from './CashFlowTab';
import * as queries from '../lib/queries';
import type { CashFlowResponse } from '../lib/types';

// Mock the queries module
vi.mock('../lib/queries');

const mockUseCashFlow = vi.mocked(queries.useCashFlow);

function renderCashFlowTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <CashFlowTab />
    </QueryClientProvider>,
  );
}

function mockQuerySuccess<T>(data: T): UseQueryResult<T, Error> {
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

function mockQueryLoading<T>(): UseQueryResult<T, Error> {
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

function mockQueryError<T>(): UseQueryResult<T, Error> {
  return {
    data: undefined,
    status: 'error',
    isLoading: false,
    isError: true,
    error: new Error('Query failed'),
    fetchStatus: 'idle',
    isPending: false,
    isSuccess: false,
    isFetching: false,
    isStale: true,
    isPlaceholderData: false,
    failureCount: 1,
    failureReason: new Error('Query failed'),
    refetch: vi.fn(),
    remove: vi.fn(),
    dataUpdatedAt: 0,
    errorUpdatedAt: Date.now(),
  } as unknown as UseQueryResult<T, Error>;
}

describe('CashFlowTab', () => {
  beforeEach(() => {
    mockUseCashFlow.mockReset();
  });

  it('renders loading state when data is loading', () => {
    mockUseCashFlow.mockReturnValue(mockQueryLoading<CashFlowResponse>());

    renderCashFlowTab();

    expect(screen.getByText('Loading cash flow data...')).toBeInTheDocument();
  });

  it('renders error state when query fails', () => {
    mockUseCashFlow.mockReturnValue(mockQueryError<CashFlowResponse>());

    renderCashFlowTab();

    expect(screen.getByText(/failed to load cash flow data/i)).toBeInTheDocument();
  });

  it('renders empty state when no data is available', () => {
    mockUseCashFlow.mockReturnValue({
      data: undefined,
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
    } as unknown as UseQueryResult<CashFlowResponse, Error>);

    renderCashFlowTab();

    expect(screen.getByText('No cash flow data available.')).toBeInTheDocument();
  });

  it('renders key metrics when data is available', () => {
    const mockData: CashFlowResponse = {
      income: 5000,
      expenses: 3000,
      net_flow: 2000,
      transfer_count: 5,
      flagged_count: 2,
      savings_rate: 0.4,
      month_over_month: [
        { month: '2024-01', tx_type: 'INCOME', amount: 5000 },
        { month: '2024-01', tx_type: 'EXPENSE', amount: 3000 },
        { month: '2024-02', tx_type: 'INCOME', amount: 5200 },
        { month: '2024-02', tx_type: 'EXPENSE', amount: 3100 },
      ],
      weekly_trend: [],
      rolling_30d_spend: [
        { date: '2024-02-01', amount: 100 },
        { date: '2024-02-02', amount: 150 },
      ],
      monthly_net_by_owner: [],
      category_distribution: [],
    };
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(mockData));

    renderCashFlowTab();

    // Check that the heading is rendered
    expect(screen.getByText('Cash Flow')).toBeInTheDocument();

    // Check that key metric labels are rendered
    expect(screen.getByText('Total Income')).toBeInTheDocument();
    expect(screen.getByText('Total Expenses')).toBeInTheDocument();
    expect(screen.getByText('Net Flow')).toBeInTheDocument();
    expect(screen.getByText('Savings Rate')).toBeInTheDocument();
    expect(screen.getByText('Transfers')).toBeInTheDocument();
    expect(screen.getByText('Flagged')).toBeInTheDocument();
  });

  it('renders income vs expenses chart when month data is available', () => {
    const mockData: CashFlowResponse = {
      income: 5000,
      expenses: 3000,
      net_flow: 2000,
      transfer_count: 5,
      flagged_count: 2,
      savings_rate: 0.4,
      month_over_month: [
        { month: '2024-01', tx_type: 'INCOME', amount: 5000 },
        { month: '2024-01', tx_type: 'EXPENSE', amount: 3000 },
      ],
      weekly_trend: [],
      rolling_30d_spend: [],
      monthly_net_by_owner: [],
      category_distribution: [],
    };
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(mockData));

    renderCashFlowTab();

    expect(screen.getByText('Income vs Expenses')).toBeInTheDocument();
  });

  it('renders rolling spend chart when rolling spend data is available', () => {
    const mockData: CashFlowResponse = {
      income: 5000,
      expenses: 3000,
      net_flow: 2000,
      transfer_count: 5,
      flagged_count: 2,
      savings_rate: 0.4,
      month_over_month: [],
      weekly_trend: [],
      rolling_30d_spend: [
        { date: '2024-02-01', amount: 100 },
        { date: '2024-02-02', amount: 150 },
      ],
      monthly_net_by_owner: [],
      category_distribution: [],
    };
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(mockData));

    renderCashFlowTab();

    expect(screen.getByText('30-Day Rolling Spend')).toBeInTheDocument();
  });

  it('displays formatted currency values', () => {
    const mockData: CashFlowResponse = {
      income: 5000,
      expenses: 3000,
      net_flow: 2000,
      transfer_count: 5,
      flagged_count: 2,
      savings_rate: 0.4,
      month_over_month: [],
      weekly_trend: [],
      rolling_30d_spend: [],
      monthly_net_by_owner: [],
      category_distribution: [],
    };
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(mockData));

    renderCashFlowTab();

    // Check that currency values are rendered by looking for formatted amounts
    expect(screen.getByText(/\$5,000/)).toBeInTheDocument();
    expect(screen.getByText(/\$3,000/)).toBeInTheDocument();
  });

  it('displays percentage for savings rate', () => {
    const mockData: CashFlowResponse = {
      income: 5000,
      expenses: 3000,
      net_flow: 2000,
      transfer_count: 5,
      flagged_count: 2,
      savings_rate: 0.4,
      month_over_month: [],
      weekly_trend: [],
      rolling_30d_spend: [],
      monthly_net_by_owner: [],
      category_distribution: [],
    };
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(mockData));

    renderCashFlowTab();

    expect(screen.getByText(/40\.0%/)).toBeInTheDocument();
  });
});
