import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { OverviewTab } from './OverviewTab';
import { FilterProvider } from '../lib/FilterContext';
import type { OverviewResponse } from '../lib/types';
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query';

// OverviewTab reads `useFilters()` directly (Fix 14 cross-filtering), so it
// needs a real FilterProvider ancestor even though `useOverview` is mocked.
function renderOverviewTab() {
  return render(
    <FilterProvider>
      <OverviewTab />
    </FilterProvider>,
  );
}

// Mock the queries module
vi.mock('../lib/queries', () => ({
  useOverview: vi.fn(),
}));

// Mock the mutations module — useSetCreditLimit() is the credit-limit editor's
// only dependency outside props.
vi.mock('../lib/mutations', () => ({
  useSetCreditLimit: vi.fn(),
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
import { useSetCreditLimit } from '../lib/mutations';

const mockedUseOverview = vi.mocked(useOverview);
const mockedUseSetCreditLimit = vi.mocked(useSetCreditLimit);

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
    metrics: {
      avg_monthly_income: {
        key: 'avg_monthly_income',
        value: 15000,
        baseline: 13000,
        delta_pct: 0.1538,
        baseline_months: 3,
        sparkline: [12000, 13500, 15000],
      },
      avg_monthly_expense: {
        key: 'avg_monthly_expense',
        value: 7385,
        baseline: 7000,
        delta_pct: 0.055,
        baseline_months: 3,
        sparkline: [6800, 7100, 7385],
      },
      avg_monthly_net: {
        key: 'avg_monthly_net',
        value: 7615,
        baseline: 6000,
        delta_pct: 0.269,
        baseline_months: 3,
        sparkline: [5200, 6400, 7615],
      },
      savings_rate: {
        key: 'savings_rate',
        value: 0.6,
        baseline: null,
        delta_pct: null,
        baseline_months: 0,
        sparkline: [],
      },
    },
    top_categories: [
      { category: 'Groceries', amount: 1200 },
      { category: 'Utilities', amount: 350 },
      { category: 'Entertainment', amount: 400 },
    ],
    month_over_month: [
      { category: 'Groceries', period: 'this_month', amount: 1200 },
      { category: 'Groceries', period: 'last_month', amount: 1100 },
      { category: 'Utilities', period: 'this_month', amount: 300 },
      { category: 'Utilities', period: 'last_month', amount: 280 },
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

const mockMutate = vi.fn();

describe('OverviewTab', () => {
  beforeEach(() => {
    mockedUseOverview.mockReset();
    mockMutate.mockReset();
    mockedUseSetCreditLimit.mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    } as unknown as UseMutationResult<void, Error, { accountKey: string; limit: number | null }>);
  });

  // FilterProvider syncs filter state to the URL via replaceState; reset it so
  // one test's click-to-filter doesn't leak into the next test's initial
  // filter state via a shared jsdom `window`.
  afterEach(() => {
    window.history.replaceState(null, '', window.location.pathname);
  });

  it('renders a skeleton while data is being fetched', () => {
    mockedUseOverview.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    // The skeleton replaces the old bare "Loading overview..." string with
    // layout-shaped placeholder blocks (PLAN.md Phase 15, Fix 14).
    expect(screen.getByRole('status', { name: 'Loading…' })).toBeInTheDocument();
  });

  it('renders error state when query fails, with a retry action wired to refetch', () => {
    const errorMsg = 'Failed to fetch overview';
    const refetch = vi.fn();
    mockedUseOverview.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error(errorMsg),
      refetch,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    expect(screen.getByText(errorMsg)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(refetch).toHaveBeenCalled();
  });

  it('renders no data message when data is null', () => {
    mockedUseOverview.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

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

    renderOverviewTab();

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

    renderOverviewTab();

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

    renderOverviewTab();

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

    renderOverviewTab();

    expect(screen.getAllByText('not enough complete months').length).toBe(3);
  });

  it('renders savings rate trend chart with a footnote for hidden null months', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    expect(screen.getByText('Savings Rate Trend')).toBeInTheDocument();
    // One month (2026-02) has savings_rate: null in the fixture.
    expect(screen.getByText('1 month hidden — no recorded income.')).toBeInTheDocument();
  });

  it('renders no brush/zoom control on the savings rate trend chart -- a short, filter-bounded series has no use for one', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    const { container } = renderOverviewTab();

    const heading = screen.getByText('Savings Rate Trend');
    const card = heading.closest('.rounded-lg') as HTMLElement;
    expect(card.querySelector('.recharts-brush')).toBeNull();
    expect(container).toContainElement(card);
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

    renderOverviewTab();

    expect(screen.getByText('Savings Rate Trend')).toBeInTheDocument();
    expect(screen.queryByText(/hidden — no recorded income/)).not.toBeInTheDocument();
  });

  it('renders asset mix chart', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    expect(screen.getByText('Asset Mix')).toBeInTheDocument();
  });

  it('renders owner balances as one mini chart per owner, with every account name and balance visible without hovering', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    const heading = screen.getByText('Owner Balances');
    const chartCard = heading.closest('div');
    expect(chartCard).not.toBeNull();
    const withinCard = within(chartCard!);

    // One mini chart heading per owner (small multiples, not a shared axis).
    expect(withinCard.getByText('Alice')).toBeInTheDocument();
    expect(withinCard.getByText('Bob')).toBeInTheDocument();

    // Every account name is a category-axis tick label, and every balance is
    // a direct value label on its bar -- both rendered without hovering.
    for (const owner of mockOverviewData.net_worth.owner_balances) {
      for (const account of owner.accounts) {
        expect(withinCard.getByText(account.account_name)).toBeInTheDocument();
      }
    }
    expect(withinCard.getByText('$100,000')).toBeInTheDocument();
    expect(withinCard.getByText('$150,000')).toBeInTheDocument();
  });

  it('renders top categories chart', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    expect(screen.getByText('Top Expense Categories')).toBeInTheDocument();
  });

  it('renders emergency fund months when available', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    // Fix 10: the bare tile became a card with a progress bar toward the
    // 6-month goal — see "renders an emergency fund progress bar..." below.
    expect(screen.getByText('Emergency Fund')).toBeInTheDocument();
    expect(screen.getByText('4.5 months')).toBeInTheDocument();
  });

  it('renders flagged transactions count', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    // Label comes from the metricInfo registry now (Fix 13): "Flagged", not
    // "Flagged Transactions" -- one source of truth so label and tooltip agree.
    expect(screen.getByText('Flagged')).toBeInTheDocument();
  });

  it('renders sync-health warning for stale accounts, with correct wording', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

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

    renderOverviewTab();

    expect(screen.queryByText('Balances may be out of date')).not.toBeInTheDocument();
  });

  it('renders dormant accounts as a collapsed details block, separate from sync health', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    expect(screen.getByText('1 account with no activity in 90+ days')).toBeInTheDocument();
    expect(screen.getByText(/Forgotten Savings.*no activity in 120 days/)).toBeInTheDocument();
  });

  it('renders credit utilization with a progress bar and manual-limit marker', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    const heading = screen.getByText('Credit Utilization');
    const card = heading.closest('div');
    expect(card).not.toBeNull();
    const withinCard = within(card!);
    // "Chase Card — Alice" appears twice — once in the utilization row, once
    // in the collapsible limit editor below it.
    expect(withinCard.getAllByText(/Chase Card — Alice/).length).toBe(2);
    expect(withinCard.getByText(/\$2,500 \/ \$10,000 \(25\.0% used\)/)).toBeInTheDocument();
    const bar = withinCard.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-valuenow', '25');
    // is_manual is false in the fixture row, so no "manually set" marker.
    expect(withinCard.queryByText(/manually set/)).not.toBeInTheDocument();
  });

  it('shows the manual-limit marker when is_manual is true', () => {
    const withManualLimit: OverviewResponse = {
      ...mockOverviewData,
      net_worth: {
        ...mockOverviewData.net_worth,
        credit_utilization: [
          {
            account_key: 'acct-manual',
            account_name: 'Amex Card',
            owner_name: 'Bob',
            current: 500,
            limit: 5000,
            pct: 0.1,
            is_manual: true,
          },
        ],
      },
    };
    mockedUseOverview.mockReturnValue({
      data: withManualLimit,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    expect(screen.getByText(/manually set limit/)).toBeInTheDocument();
  });

  it('renders "no credit limit set" with no progress bar when limit is null', () => {
    const noLimit: OverviewResponse = {
      ...mockOverviewData,
      net_worth: {
        ...mockOverviewData.net_worth,
        credit_utilization: [
          {
            account_key: 'acct-nolimit',
            account_name: 'Store Card',
            owner_name: 'Alice',
            current: 340,
            limit: null,
            pct: null,
            is_manual: false,
          },
        ],
      },
    };
    mockedUseOverview.mockReturnValue({
      data: noLimit,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    const heading = screen.getByText('Credit Utilization');
    const card = heading.closest('div');
    expect(card).not.toBeNull();
    const withinCard = within(card!);
    expect(withinCard.getByText(/Store Card — Alice — \$340 owed — no credit limit set/)).toBeInTheDocument();
    // No progress bar for the row itself. (The credit-limit editor below still
    // has a text input for this card, which is expected.)
    expect(withinCard.queryByRole('progressbar')).not.toBeInTheDocument();
  });

  // Standard "lower is better" credit-utilization guidance: <30% healthy,
  // 30-60% elevated, >=60% serious. Covers both boundaries plus one case per band.
  it.each([
    [0.95, 'bg-serious'],
    [0.6, 'bg-serious'],
    [0.45, 'bg-warn'],
    [0.3, 'bg-warn'],
    [0.1, 'bg-pos'],
  ])('renders utilization %s with meter class %s', (pct, expectedClass) => {
    const data: OverviewResponse = {
      ...mockOverviewData,
      net_worth: {
        ...mockOverviewData.net_worth,
        credit_utilization: [
          {
            account_key: 'acct-tone-test',
            account_name: 'Tone Test Card',
            owner_name: 'Alice',
            current: pct * 1000,
            limit: 1000,
            pct,
            is_manual: false,
          },
        ],
      },
    };
    mockedUseOverview.mockReturnValue({
      data,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    // Scoped to the Credit Utilization card specifically -- Emergency Fund
    // (elsewhere on the page) also renders a `[role="progressbar"]` meter, and
    // its position relative to Credit Utilization is not guaranteed by the
    // card-pairing layout, so a page-wide "first progressbar" query is fragile.
    const card = screen.getByText('Credit Utilization').closest('div');
    const meterFill = card!.querySelector('[role="progressbar"] > div');
    expect(meterFill).not.toBeNull();
    expect(meterFill).toHaveClass(expectedClass);
  });

  it('does not render the credit section when there are no credit cards', () => {
    const noCredit: OverviewResponse = {
      ...mockOverviewData,
      net_worth: { ...mockOverviewData.net_worth, credit_utilization: [] },
    };
    mockedUseOverview.mockReturnValue({
      data: noCredit,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    expect(screen.queryByText('Credit Utilization')).not.toBeInTheDocument();
  });

  it('credit limit editor calls the mutation with the right account_key and value', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    const input = screen.getByLabelText('Credit limit for Chase Card');
    fireEvent.change(input, { target: { value: '5000' } });
    const saveButtons = screen.getAllByRole('button', { name: 'Save' });
    fireEvent.click(saveButtons[0]);

    expect(mockMutate).toHaveBeenCalledWith({ accountKey: 'acct-chase', limit: 5000 });
  });

  it('renders a duplicate-account warning only when forked_accounts is non-empty', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);
    const { rerender } = renderOverviewTab();

    expect(screen.queryByText('These accounts appear more than once')).not.toBeInTheDocument();

    const withForkedAccounts: OverviewResponse = {
      ...mockOverviewData,
      net_worth: { ...mockOverviewData.net_worth, forked_accounts: ['Joint Checking', 'Old Savings'] },
    };
    mockedUseOverview.mockReturnValue({
      data: withForkedAccounts,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);
    rerender(
      <FilterProvider>
        <OverviewTab />
      </FilterProvider>,
    );

    expect(screen.getByText('These accounts appear more than once')).toBeInTheDocument();
    expect(screen.getByText('Joint Checking, Old Savings')).toBeInTheDocument();
  });

  it('renders income sources as a sorted horizontal bar chart', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    expect(screen.getByText('Income Sources')).toBeInTheDocument();
  });

  it('renders month-over-month by category as a grouped bar chart', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    expect(screen.getByText('Month-over-Month by Category')).toBeInTheDocument();
  });

  it('renders an emergency fund progress bar with the explanatory caption', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    expect(screen.getByText('Emergency Fund')).toBeInTheDocument();
    expect(screen.getByText('Liquid savings ÷ average monthly expenses.')).toBeInTheDocument();
    expect(screen.getByText('4.5 months')).toBeInTheDocument();
  });

  it('renders the weekly income tile beside weekly expenses', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    expect(screen.getByText('Weekly Expenses')).toBeInTheDocument();
    expect(screen.getByText('$1,846')).toBeInTheDocument();
    expect(screen.getByText('Weekly Income')).toBeInTheDocument();
    expect(screen.getByText('$3,462')).toBeInTheDocument();
  });

  it('renders a baseline comparison for a metric tile with API-provided context', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    // avg_monthly_income: delta_pct 0.1538 vs a 3-month baseline -> "15% above ...".
    expect(screen.getByText('15% above your 3-month average')).toBeInTheDocument();
  });

  it('renders no comparison when a metric has no baseline (savings_rate in the fixture)', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    expect(screen.queryByText(/vs your .*-month average/)).not.toBeInTheDocument();
  });

  it('opens the metric info tooltip by keyboard and closes it on Escape (Fix 13)', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    const trigger = screen.getByRole('button', { name: 'More about Net Worth' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');

    trigger.focus();
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText("What you'd have left if you settled every account today.")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(document.activeElement).toBe(trigger);
  });

  it('patches the category filter when a Top Categories bar is clicked (Fix 14)', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    const { container } = renderOverviewTab();

    const heading = screen.getByText('Top Expense Categories');
    const card = heading.closest('div');
    expect(card).not.toBeNull();
    const bar = card!.querySelectorAll('.recharts-bar-rectangle')[0];
    expect(bar).toBeTruthy();
    fireEvent.click(bar!);

    expect(new URLSearchParams(window.location.search).getAll('categories')).toContain('Groceries');
    expect(container).toContainElement(card);
  });

  it('renders a discoverability hint above the clickable Top Categories chart', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    expect(screen.getByText('Click a bar to add that category to your filters.')).toBeInTheDocument();
  });
});
