import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen } from '@testing-library/react';
import { OverviewTab } from './OverviewTab';
import type { OverviewResponse } from '../lib/types';
import type { UseQueryResult } from '@tanstack/react-query';

// Mock the queries module
vi.mock('../lib/queries', () => ({
  useOverview: vi.fn(),
}));

// Recharts' ResponsiveContainer measures its parent via ResizeObserver, which
// jsdom doesn't implement, so charts never receive a nonzero size and render
// no children. Give the wrapped chart an explicit fixed size instead.
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
      {
        owner: 'Alice',
        depository: 100000,
        investment: 200000,
        credit: -5000,
        other: 0,
        net: 295000,
        accounts: [
          { account_name: 'Alice Checking', type: 'depository', value: 100000 },
          { account_name: 'Alice Brokerage', type: 'investment', value: 200000 },
          { account_name: 'Alice Card', type: 'credit', value: -5000 },
        ],
      },
      {
        owner: 'Bob',
        depository: 150000,
        investment: 50000,
        credit: -2000,
        other: 0,
        net: 198000,
        accounts: [
          { account_name: 'Bob Checking', type: 'depository', value: 150000 },
          { account_name: 'Bob Brokerage', type: 'investment', value: 50000 },
          { account_name: 'Bob Card', type: 'credit', value: -2000 },
        ],
      },
    ],
    credit_utilization: [
      {
        account_key: 'acct-chase',
        account_name: 'Chase Card',
        owner_name: 'Alice',
        current: 2500,
        limit: 10000,
        pct: 0.25,
        is_manual: false,
      },
    ],
    stale_accounts: [{ account_key: 'acct-old-savings', account_name: 'Old Savings', days_stale: 45 }],
    dormant_accounts: [
      {
        account_key: 'acct-dormant',
        account_name: 'Forgotten Savings',
        owner_name: 'Alice',
        days_inactive: 120,
        balance: 300,
      },
    ],
    forked_accounts: [],
  },
  overview: {
    income: 15000,
    expenses: 8000,
    net_flow: 7000,
    savings_rate: 0.6,
    flagged_count: 2,
    avg_weekly_expense: 1846,
    avg_monthly_expense: 7385,
    avg_weekly_income: 3462,
    avg_monthly_income: 15000,
    avg_monthly_net: 7615,
    complete_months: 3,
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
      { month: '2026-01', savings_rate: 0.45, income: 15000, expenses: 8250 },
      { month: '2026-02', savings_rate: null, income: 0, expenses: 500 },
      { month: '2026-03', savings_rate: 0.6, income: 15000, expenses: 6000 },
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

  it('renders the overview even when net worth is legitimately zero', () => {
    const zeroNetWorthData: OverviewResponse = {
      ...mockOverviewData,
      net_worth: {
        ...mockOverviewData.net_worth,
        net_worth: 0,
      },
    };
    mockedUseOverview.mockReturnValue({
      data: zeroNetWorthData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    expect(screen.queryByText('No data available')).not.toBeInTheDocument();
    const netWorthLabel = screen.getByText('Net Worth');
    const netWorthTile = netWorthLabel.closest('div');
    expect(netWorthTile).not.toBeNull();
    expect(netWorthTile).toHaveTextContent('$0');
  });

  it('renders key stat tiles with net worth and savings rate as a correctly-scaled percentage', () => {
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
    // 0.6 must render as 60.0%, not 6000.0% (double-scaling bug).
    expect(screen.getByText('60.0%')).toBeInTheDocument();
    expect(screen.queryByText('6000.0%')).not.toBeInTheDocument();
  });

  it('renders income and expenses tiles using the monthly-average figures', () => {
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

    // Net Monthly Flow must use avg_monthly_net, not the all-time net_flow.
    expect(screen.getByText('Net Monthly Flow')).toBeInTheDocument();
    expect(screen.getByText('$7,615')).toBeInTheDocument();
    expect(screen.queryByText('$7,000')).not.toBeInTheDocument();

    expect(screen.getAllByText('avg of 3 complete months').length).toBe(3);
  });

  it('shows "not enough complete months" when complete_months is 0', () => {
    const noCompleteMonths: OverviewResponse = {
      ...mockOverviewData,
      overview: { ...mockOverviewData.overview, complete_months: 0 },
    };
    mockedUseOverview.mockReturnValue({
      data: noCompleteMonths,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    expect(screen.getAllByText('not enough complete months').length).toBe(3);
  });

  it('renders savings rate trend chart with a footnote for hidden null months', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    expect(screen.getByText('Savings Rate Trend')).toBeInTheDocument();
    // One month (2026-02) has savings_rate: null in the fixture.
    expect(screen.getByText('1 month hidden — no recorded income.')).toBeInTheDocument();
  });

  it('does not crash and shows no footnote when no months are null', () => {
    const noNullMonths: OverviewResponse = {
      ...mockOverviewData,
      overview: {
        ...mockOverviewData.overview,
        savings_rate_trend: [{ month: '2026-01', savings_rate: 0.5, income: 15000, expenses: 7500 }],
      },
    };
    mockedUseOverview.mockReturnValue({
      data: noNullMonths,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    expect(screen.getByText('Savings Rate Trend')).toBeInTheDocument();
    expect(screen.queryByText(/hidden — no recorded income/)).not.toBeInTheDocument();
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

  it('renders owner balances chart with exactly one x-axis tick per owner', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    const heading = screen.getByText('Owner Balances');
    const chartCard = heading.closest('div');
    expect(chartCard).not.toBeNull();
    // Recharts renders axis tick labels in a separate z-index layer, sibling
    // to (not nested under) the `.recharts-xAxis` group.
    const tickLabels = Array.from(chartCard!.querySelectorAll('.recharts-xAxis-tick-labels text'))
      .map((el) => el.textContent)
      .filter((text): text is string => !!text);
    expect(tickLabels.length).toBe(mockOverviewData.net_worth.owner_balances.length);
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
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

  it('renders sync-health warning for stale accounts, with correct wording', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    expect(screen.getByText('Balances may be out of date')).toBeInTheDocument();
    expect(screen.getByText(/Old Savings.*balance last refreshed 45 days ago/)).toBeInTheDocument();
    expect(screen.getByText(/Plaid connection/)).toBeInTheDocument();
  });

  it('does not render sync-health section when stale accounts is empty', () => {
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

    expect(screen.queryByText('Balances may be out of date')).not.toBeInTheDocument();
  });

  it('renders dormant accounts as a collapsed details block, separate from sync health', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    render(<OverviewTab />);

    expect(screen.getByText('1 account with no activity in 90+ days')).toBeInTheDocument();
    expect(screen.getByText(/Forgotten Savings.*no activity in 120 days/)).toBeInTheDocument();
  });
});
