import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import type { UseQueryResult } from '@tanstack/react-query';
import { HomeTab } from './HomeTab';
import * as queries from '../lib/queries';
import type { HomeResponse } from '../lib/types';

vi.mock('../lib/queries');

// Recharts' ResponsiveContainer measures its parent via ResizeObserver, which
// jsdom doesn't implement, so charts never receive a nonzero size and render
// no children. Give the wrapped chart an explicit fixed size instead, same
// workaround the other tab tests use.
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

const mockUseHome = vi.mocked(queries.useHome);

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

const emptyData: HomeResponse = {
  net_worth_trend: [],
  recurring_monthly_spend: 0,
  recurring_items: [],
  top_merchants: [],
  cash_flow_projection: null,
  category_drift: [],
  subscriptions: [],
};

const fullData: HomeResponse = {
  net_worth_trend: [
    { date: '2026-08-23', net_worth: 900 },
    { date: '2026-08-24', net_worth: 1000 },
  ],
  recurring_monthly_spend: 50,
  recurring_items: [{ description: 'Gym Membership', amount: 50 }],
  top_merchants: [{ description: 'Amazon', amount: 250 }],
  cash_flow_projection: {
    month: '2026-08',
    spent_so_far: 400,
    income_so_far: 2000,
    projected_expenses: 800,
    projected_income: 4000,
    days_elapsed: 12,
    days_in_month: 31,
  },
  category_drift: [{ category: 'Groceries', current: 140, baseline: 100, drift_pct: 0.4 }],
  subscriptions: [{ description: 'Streaming Service', average_amount: 9.99, months_seen: 3 }],
};

describe('HomeTab', () => {
  beforeEach(() => {
    mockUseHome.mockReset();
  });

  it('renders a skeleton while data is loading', () => {
    mockUseHome.mockReturnValue(mockQueryLoading<HomeResponse>());
    render(<HomeTab />);
    expect(screen.getByRole('status', { name: 'Loading…' })).toBeInTheDocument();
  });

  it('renders error state when the query fails, with a retry action wired to refetch', () => {
    const refetch = vi.fn();
    mockUseHome.mockReturnValue({ ...mockQueryError<HomeResponse>(), refetch });
    render(<HomeTab />);

    expect(screen.getByText('Query failed')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(refetch).toHaveBeenCalled();
  });

  it('renders "no data available" rather than crashing when data is missing expected fields', () => {
    // Reproduces the shape a shared/generic API mock can hand back (e.g.
    // App.test.tsx's blanket apiFetch mock resolves every endpoint to an
    // auth-shaped object): `data` itself is truthy, but none of the fields
    // this tab reads exist on it.
    mockUseHome.mockReturnValue(mockQuerySuccess({ unrelated: true } as unknown as HomeResponse));
    render(<HomeTab />);
    expect(screen.getByText('No data available')).toBeInTheDocument();
  });

  it('renders empty-state notes for every insight when there is no data yet', () => {
    mockUseHome.mockReturnValue(mockQuerySuccess(emptyData));
    render(<HomeTab />);

    expect(screen.getByText(/history starts the day balance tracking shipped/i)).toBeInTheDocument();
    expect(screen.getByText(/not enough expense history yet/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing flagged recurring yet/i)).toBeInTheDocument();
    expect(screen.getByText(/not enough history yet to compare this month/i)).toBeInTheDocument();
    expect(screen.getByText(/none detected in the trailing 6 months/i)).toBeInTheDocument();
    // No net-worth-history yet -> no "current net worth" tile.
    expect(screen.queryByText('Net Worth')).not.toBeInTheDocument();
  });

  it('renders the net worth trend chart once there are at least 2 snapshots', () => {
    mockUseHome.mockReturnValue(mockQuerySuccess(fullData));
    const { container } = render(<HomeTab />);
    expect(container.querySelector('.recharts-line')).toBeInTheDocument();
  });

  it('renders the latest net worth as the headline tile', () => {
    mockUseHome.mockReturnValue(mockQuerySuccess(fullData));
    render(<HomeTab />);
    expect(screen.getByText('Net Worth')).toBeInTheDocument();
    // "$1,000" can also appear as a chart axis tick, so assert presence rather
    // than uniqueness.
    expect(screen.getAllByText('$1,000').length).toBeGreaterThan(0);
  });

  it('renders recurring spend, merchants, and subscriptions', () => {
    mockUseHome.mockReturnValue(mockQuerySuccess(fullData));
    render(<HomeTab />);
    expect(screen.getByText('Gym Membership')).toBeInTheDocument();
    expect(screen.getByText('Amazon')).toBeInTheDocument();
    expect(screen.getByText('Streaming Service')).toBeInTheDocument();
    expect(screen.getByText('$10/mo')).toBeInTheDocument();
  });

  it('colors category drift by tone: overspending renders in the "bad" token', () => {
    mockUseHome.mockReturnValue(mockQuerySuccess(fullData));
    render(<HomeTab />);
    const driftValue = screen.getByText(/40\.0%/);
    expect(driftValue).toHaveStyle({ color: 'var(--neg-text)' });
  });

  it('shows the month-end projection tile with progress context', () => {
    mockUseHome.mockReturnValue(mockQuerySuccess(fullData));
    render(<HomeTab />);
    expect(screen.getByText('Projected Month-End Spend')).toBeInTheDocument();
    expect(screen.getByText('day 12 of 31')).toBeInTheDocument();
  });
});
