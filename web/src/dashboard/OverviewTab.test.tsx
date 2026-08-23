import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { OverviewTab } from './OverviewTab';
import type { OverviewResponse } from '../lib/types';
import type { UseQueryResult } from '@tanstack/react-query';

// Mock the queries module
vi.mock('../lib/queries', () => ({
  useOverview: vi.fn(),
}));

import { useOverview } from '../lib/queries';

const mockedUseOverview = vi.mocked(useOverview);

const mockOverviewData: OverviewResponse = {
  net_worth: {
    net_worth: 500000,
    total_assets: 750000,
    total_liabilities: 250000,
    asset_mix: [
      { subtype_label: 'Checking', balance: 25000 },
      { subtype_label: 'Savings', balance: 50000 },
      { subtype_label: 'Investment', balance: 675000 },
    ],
    owner_balances: [
      { owner: 'Alice', value: 300000, type: 'assets' },
      { owner: 'Bob', value: 200000, type: 'assets' },
    ],
    credit_utilization: [
      {
        account_name: 'Chase Card',
        owner_name: 'Alice',
        current: 2500,
        limit: 10000,
        pct: 0.25,
        is_manual: false,
      },
    ],
    stale_accounts: [{ account_name: 'Old Savings', days_stale: 45 }],
    forked_accounts: [],
  },
  overview: {
    income: 15000,
    expenses: 8000,
    net_flow: 7000,
    savings_rate: 0.467,
    flagged_count: 2,
    avg_weekly_expense: 1846,
    avg_monthly_expense: 7385,
    avg_weekly_income: 3462,
    avg_monthly_income: 15000,
    top_categories: [
      { category: 'Groceries', amount: 1200 },
      { category: 'Utilities', amount: 350 },
      { category: 'Entertainment', amount: 400 },
    ],
    month_over_month: [
      { category: 'Groceries', period: '2026-01', amount: 1100 },
      { category: 'Groceries', period: '2026-02', amount: 1200 },
    ],
    emergency_fund_months: 4.5,
    income_breakdown: [
      { description: 'Salary', amount: 12000 },
      { description: 'Freelance', amount: 3000 },
    ],
    savings_rate_trend: [
      { month: '2026-01', savings_rate: 0.45 },
      { month: '2026-02', savings_rate: 0.48 },
      { month: '2026-03', savings_rate: 0.467 },
    ],
  },
};

describe('OverviewTab', () => {
  beforeEach(() => {
    mockedUseOverview.mockReset();
  });

  it('renders loading state while data is being fetched', () => {
    mockedUseOverview.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    expect(screen.getByText('Loading overview...')).toBeInTheDocument();
  });

  it('renders error state when query fails', () => {
    const errorMsg = 'Failed to fetch overview';
    mockedUseOverview.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error(errorMsg),
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    expect(screen.getByText('Error loading overview')).toBeInTheDocument();
    expect(screen.getByText(errorMsg)).toBeInTheDocument();
  });

  it('renders no data message when data is null', () => {
    mockedUseOverview.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    expect(screen.getByText('No data available')).toBeInTheDocument();
  });

  it('renders key stat tiles with net worth and savings rate', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    expect(screen.getByText('Net Worth')).toBeInTheDocument();
    expect(screen.getByText('$500,000')).toBeInTheDocument();

    expect(screen.getByText('Total Assets')).toBeInTheDocument();
    expect(screen.getByText('$750,000')).toBeInTheDocument();

    expect(screen.getByText('Total Liabilities')).toBeInTheDocument();
    expect(screen.getByText('$250,000')).toBeInTheDocument();

    expect(screen.getByText('Savings Rate')).toBeInTheDocument();
    expect(screen.getByText('46.7%')).toBeInTheDocument();
  });

  it('renders income and expenses tiles', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    expect(screen.getByText('Monthly Income')).toBeInTheDocument();
    expect(screen.getByText('$15,000')).toBeInTheDocument();

    expect(screen.getByText('Monthly Expenses')).toBeInTheDocument();
    expect(screen.getByText('$7,385')).toBeInTheDocument();

    expect(screen.getByText('Net Monthly Flow')).toBeInTheDocument();
    expect(screen.getByText('$7,000')).toBeInTheDocument();
  });

  it('renders savings rate trend chart', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    expect(screen.getByText('Savings Rate Trend')).toBeInTheDocument();
  });

  it('renders asset mix chart', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    expect(screen.getByText('Asset Mix')).toBeInTheDocument();
  });

  it('renders owner balances chart', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    expect(screen.getByText('Owner Balances')).toBeInTheDocument();
  });

  it('renders top categories chart', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    expect(screen.getByText('Top Expense Categories')).toBeInTheDocument();
  });

  it('renders emergency fund months when available', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    expect(screen.getByText('Emergency Fund Months')).toBeInTheDocument();
    // Check that the numeric value is present
    const elements = screen.getAllByText(/^4\.5$/);
    expect(elements.length).toBeGreaterThan(0);
  });

  it('renders flagged transactions count', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    expect(screen.getByText('Flagged Transactions')).toBeInTheDocument();
  });

  it('renders stale accounts warning when present', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    expect(screen.getByText('Stale Accounts')).toBeInTheDocument();
    expect(screen.getByText(/Old Savings.*45 days/)).toBeInTheDocument();
  });

  it('does not render stale accounts section when empty', () => {
    const dataWithoutStaleAccounts = {
      ...mockOverviewData,
      net_worth: {
        ...mockOverviewData.net_worth,
        stale_accounts: [],
      },
    };

    mockedUseOverview.mockReturnValue({
      data: dataWithoutStaleAccounts,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    expect(screen.queryByText('Stale Accounts')).not.toBeInTheDocument();
  });
});
