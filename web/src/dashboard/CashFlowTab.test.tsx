import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { UseQueryResult } from '@tanstack/react-query';
import { CashFlowTab } from './CashFlowTab';
import * as queries from '../lib/queries';
import type { CashFlowResponse } from '../lib/types';

// Mock the queries module
vi.mock('../lib/queries');

// Recharts' ResponsiveContainer measures its parent via ResizeObserver, which
// jsdom doesn't implement, so charts never receive a nonzero size and render
// no children (bars, lines, etc). Give the wrapped chart an explicit fixed
// size instead so chart internals actually render in tests.
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

const baseMockData: CashFlowResponse = {
  income: 5000,
  expenses: 3000,
  net_flow: 2000,
  transfer_count: 5,
  flagged_count: 2,
  savings_rate: 0.4,
  month_over_month: [
    { month: '2024-01', income: 5000, expenses: 3000, net: 2000 },
    { month: '2024-02', income: 5200, expenses: 3100, net: 2100 },
  ],
  weekly_trend: [
    { week: '2024-W05', income: 1200, expenses: 800, net: 400 },
    { week: '2024-W06', income: 1300, expenses: 900, net: 400 },
  ],
  rolling_30d_spend: [
    { date: '2024-02-01', amount: 100, daily_avg: 100 / 30 },
    { date: '2024-02-02', amount: 150, daily_avg: 150 / 30 },
  ],
  monthly_net_by_owner: [
    { month: '2024-01', owner: 'Jacob', amount: 500 },
    { month: '2024-01', owner: 'Alexie', amount: 300 },
    { month: '2024-02', owner: 'Jacob', amount: 600 },
    { month: '2024-02', owner: 'Alexie', amount: 200 },
  ],
  category_distribution: [
    { month: '2024-01', category: 'Groceries', amount: 400 },
    { month: '2024-01', category: 'Dining', amount: 150 },
    { month: '2024-02', category: 'Groceries', amount: 350 },
    { month: '2024-02', category: 'Dining', amount: 200 },
  ],
};

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
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(baseMockData));

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

  it('renders Total Expenses as a positive figure with no stray minus sign', () => {
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(baseMockData));

    renderCashFlowTab();

    expect(screen.getByText('$3,000')).toBeInTheDocument();
    expect(screen.queryByText('-$3,000')).not.toBeInTheDocument();
  });

  it('renders income vs expenses chart with actual bar elements (not an empty chart)', () => {
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(baseMockData));

    const { container } = renderCashFlowTab();

    expect(screen.getByText('Income vs Expenses')).toBeInTheDocument();
    const bars = container.querySelectorAll('.recharts-bar-rectangle');
    expect(bars.length).toBeGreaterThan(0);
    // Two bar series (income, expenses) across two months = 4 rectangles, the
    // first of several charts on the page (weekly, owner, category follow it).
    expect(bars.length).toBeGreaterThanOrEqual(4);
  });

  it('renders rolling spend chart when rolling spend data is available', () => {
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(baseMockData));

    renderCashFlowTab();

    expect(screen.getByText('Rolling 30-day spend')).toBeInTheDocument();
    expect(screen.getByText(/total spent in the 30 days ending on each date/)).toBeInTheDocument();
  });

  it('renders an actual line in the rolling spend chart (not an empty chart)', () => {
    // Scoped to this chart's own container by test id, NOT to the page: the Income vs
    // Expenses ComposedChart also renders a `.recharts-line-curve` (its net line), so a
    // container-wide query passes even when this chart has no <Line> at all. That is
    // exactly how the missing mark got here — the heading-only assertion never noticed.
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(baseMockData));

    renderCashFlowTab();

    const chart = screen.getByTestId('rolling-spend-chart');
    expect(chart.querySelectorAll('.recharts-line-curve').length).toBeGreaterThan(0);
  });

  it('displays formatted currency values', () => {
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(baseMockData));

    renderCashFlowTab();

    // Check that currency values are rendered by looking for formatted amounts
    expect(screen.getByText(/\$5,000/)).toBeInTheDocument();
    expect(screen.getByText(/\$3,000/)).toBeInTheDocument();
  });

  it('displays savings rate of 0.4 as 40.0% and not 4000.0%', () => {
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(baseMockData));

    renderCashFlowTab();

    expect(screen.getByText(/40\.0%/)).toBeInTheDocument();
    expect(screen.queryByText(/4000\.0%/)).not.toBeInTheDocument();
  });

  it('displays savings rate of 0.6 as 60.0% and not 6000.0%', () => {
    const mockData: CashFlowResponse = { ...baseMockData, savings_rate: 0.6 };
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(mockData));

    renderCashFlowTab();

    expect(screen.getByText('60.0%')).toBeInTheDocument();
    expect(screen.queryByText('6000.0%')).not.toBeInTheDocument();
  });

  it('renders the transfers-excluded caption', () => {
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(baseMockData));

    renderCashFlowTab();

    expect(
      screen.getByText('Inter-account transfers are excluded from income and expense totals.'),
    ).toBeInTheDocument();
  });

  it('renders the weekly income vs expenses chart with actual bar elements', () => {
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(baseMockData));

    renderCashFlowTab();

    const heading = screen.getByText('Income vs Expenses (weekly)');
    const card = heading.closest('.rounded-lg') as HTMLElement;
    // Two bar series (income, expenses) across two weeks = 4 rectangles.
    const bars = card.querySelectorAll('.recharts-bar-rectangle');
    expect(bars.length).toBe(4);
  });

  it('does not render the weekly chart when weekly_trend is empty', () => {
    const mockData: CashFlowResponse = { ...baseMockData, weekly_trend: [] };
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(mockData));

    renderCashFlowTab();

    expect(screen.queryByText('Income vs Expenses (weekly)')).not.toBeInTheDocument();
  });

  it('renders the monthly net cash flow by holder chart with one bar series per owner', () => {
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(baseMockData));

    renderCashFlowTab();

    expect(screen.getByText('Monthly net cash flow by holder')).toBeInTheDocument();
    // Two owners (Jacob, Alexie) named as legend entries -- identity must never
    // rest on colour matching alone.
    expect(screen.getByText('Jacob')).toBeInTheDocument();
    expect(screen.getByText('Alexie')).toBeInTheDocument();
  });

  it('renders actual bars for the monthly net cash flow by holder chart', () => {
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(baseMockData));

    renderCashFlowTab();

    const heading = screen.getByText('Monthly net cash flow by holder');
    const card = heading.closest('.rounded-lg') as HTMLElement;
    // 2 owners x 2 months = 4 rectangles.
    const bars = card.querySelectorAll('.recharts-bar-rectangle');
    expect(bars.length).toBe(4);
  });

  it('renders the monthly expense breakdown by category chart with a stacked bar per category', () => {
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(baseMockData));

    renderCashFlowTab();

    const heading = screen.getByText('Monthly expense breakdown by category');
    expect(screen.getByText('Groceries')).toBeInTheDocument();
    expect(screen.getByText('Dining')).toBeInTheDocument();
    const card = heading.closest('.rounded-lg') as HTMLElement;
    // 2 categories x 2 months = 4 rectangles.
    const bars = card.querySelectorAll('.recharts-bar-rectangle');
    expect(bars.length).toBe(4);
  });

  it('folds categories past the 8 categorical slots into "Other" instead of cycling the palette', () => {
    const manyCategories: CashFlowResponse = {
      ...baseMockData,
      category_distribution: [
        { month: '2024-01', category: 'Groceries', amount: 900 },
        { month: '2024-01', category: 'Dining', amount: 800 },
        { month: '2024-01', category: 'Rent', amount: 700 },
        { month: '2024-01', category: 'Utilities', amount: 600 },
        { month: '2024-01', category: 'Insurance', amount: 500 },
        { month: '2024-01', category: 'Subscriptions', amount: 400 },
        { month: '2024-01', category: 'Travel', amount: 300 },
        { month: '2024-01', category: 'Shopping', amount: 200 },
        { month: '2024-01', category: 'Healthcare', amount: 100 },
        { month: '2024-01', category: 'Pets', amount: 50 },
      ],
    };
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(manyCategories));

    renderCashFlowTab();

    // 10 distinct categories fold to 7 kept (highest spend) + "Other" = 8 series.
    expect(screen.getByText('Other')).toBeInTheDocument();
    expect(screen.getByText('Groceries')).toBeInTheDocument();
    // The two smallest categories (Healthcare, Pets) are folded away and no
    // longer appear as their own legend entries.
    expect(screen.queryByText('Healthcare')).not.toBeInTheDocument();
    expect(screen.queryByText('Pets')).not.toBeInTheDocument();
  });

  it('does not fold categories when there are 8 or fewer', () => {
    const eightCategories: CashFlowResponse = {
      ...baseMockData,
      category_distribution: [
        { month: '2024-01', category: 'Groceries', amount: 900 },
        { month: '2024-01', category: 'Dining', amount: 800 },
        { month: '2024-01', category: 'Rent', amount: 700 },
        { month: '2024-01', category: 'Utilities', amount: 600 },
        { month: '2024-01', category: 'Insurance', amount: 500 },
        { month: '2024-01', category: 'Subscriptions', amount: 400 },
        { month: '2024-01', category: 'Travel', amount: 300 },
        { month: '2024-01', category: 'Shopping', amount: 200 },
      ],
    };
    mockUseCashFlow.mockReturnValue(mockQuerySuccess<CashFlowResponse>(eightCategories));

    renderCashFlowTab();

    expect(screen.queryByText('Other')).not.toBeInTheDocument();
    expect(screen.getByText('Shopping')).toBeInTheDocument();
  });
});
