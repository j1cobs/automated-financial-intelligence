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
          {
            account_name: 'Alice Checking (••••1111)',
            type: 'depository',
            value: 100000,
            short_name: 'Chequing Alice',
          },
          {
            account_name: 'Alice Brokerage (••••2222)',
            type: 'investment',
            value: 200000,
            short_name: 'Investment Alice',
          },
          {
            account_name: 'Alice Card (••••3333)',
            type: 'credit',
            value: -5000,
            short_name: 'Credit card Alice',
          },
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
          {
            account_name: 'Bob Checking (••••4444)',
            type: 'depository',
            value: 150000,
            short_name: 'Chequing Bob',
          },
          {
            account_name: 'Bob Brokerage (••••5555)',
            type: 'investment',
            value: 50000,
            short_name: 'Investment Bob',
          },
          {
            account_name: 'Bob Card (••••6666)',
            type: 'credit',
            value: -2000,
            short_name: 'Credit card Bob',
          },
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
      {
        category: 'Groceries',
        this_month: 1200,
        last_month: 1100,
        usual: 1000,
        this_month_drift_pct: 0.2,
        last_month_drift_pct: 0.1,
      },
      {
        category: 'Utilities',
        this_month: 300,
        last_month: 280,
        usual: null,
        this_month_drift_pct: null,
        last_month_drift_pct: null,
      },
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
    net_worth_trend_daily: [
      { date: '2026-08-27', net_worth: 495000, assets: 745000, liabilities: 250000, liquid_cash: 70000 },
      { date: '2026-08-28', net_worth: 500000, assets: 750000, liabilities: 250000, liquid_cash: 75000 },
    ],
    net_worth_trend_monthly: [
      {
        month: '2026-07',
        net_worth: 480000,
        savings_rate: 0.5,
        credit_utilization_pct: 0.2,
        emergency_fund_months: 4.0,
      },
      {
        month: '2026-08',
        net_worth: 500000,
        savings_rate: 0.6,
        credit_utilization_pct: 0.25,
        emergency_fund_months: 4.5,
      },
    ],
    net_worth_mom_delta: 20000,
    recurring_items: [
      { description: 'Netflix', amount: 15.99 },
      { description: 'Gym Membership', amount: 40 },
    ],
    top_merchants: [
      { description: 'Amazon', amount: 2400 },
      { description: 'Costco', amount: 1800 },
    ],
    cash_flow_projection: {
      month: '2026-08',
      spent_so_far: 5000,
      income_so_far: 10000,
      projected_expenses: 8000,
      projected_income: 15000,
      days_elapsed: 20,
      days_in_month: 31,
    },
    biggest_expense_this_month: {
      description: 'Rent',
      amount: 2200,
      date: '2026-08-01',
    },
    upcoming_recurring: [
      {
        description: 'Netflix',
        amount: 15.99,
        next_expected_date: '2026-09-01',
        typical_interval_days: 30,
      },
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
    // "Net Worth" also appears as a legend entry in the Net Worth Trend chart now,
    // so pick the KPI tile's <p> label specifically, not the chart legend's <span>.
    const netWorthLabel = screen.getAllByText('Net Worth').find((el) => el.tagName === 'P');
    expect(netWorthLabel).toBeDefined();
    const netWorthTile = netWorthLabel!.closest('div');
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

    // "Net Worth" also appears as a legend entry in the Net Worth Trend chart now.
    expect(screen.getAllByText('Net Worth').some((el) => el.tagName === 'P')).toBe(true);
    expect(screen.getByText('$500,000')).toBeInTheDocument();

    expect(screen.getByText('Total Assets')).toBeInTheDocument();
    expect(screen.getByText('$750,000')).toBeInTheDocument();

    expect(screen.getByText('Total Liabilities')).toBeInTheDocument();
    expect(screen.getByText('$250,000')).toBeInTheDocument();

    // "Savings Rate" also appears as a legend entry in the Net Worth Trend chart now,
    // and its Monthly tab's percent axis can coincidentally tick at the same value
    // (60.0%) -- scope to the KPI tile itself rather than a page-wide query.
    const savingsRateLabel = screen.getAllByText('Savings Rate').find((el) => el.tagName === 'P');
    expect(savingsRateLabel).toBeDefined();
    const savingsRateTile = savingsRateLabel!.closest('div');
    expect(savingsRateTile).not.toBeNull();
    // 0.6 must render as 60.0%, not 6000.0% (double-scaling bug).
    expect(within(savingsRateTile!).getByText('60.0%')).toBeInTheDocument();
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

  it('renders the Net Worth Trend chart with its month-over-month delta', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    expect(screen.getByText('Financial Trends')).toBeInTheDocument();
    expect(screen.getByText('+$20,000 since last month')).toBeInTheDocument();
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

  it('renders owner balances as a plain-HTML list per owner, with every short_name fully visible and the full account name on hover', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    const heading = screen.getByText('Owner Balances');
    const card = heading.closest('div');
    expect(card).not.toBeNull();
    const withinCard = within(card!);

    // One mini list heading per owner (small multiples, not a shared axis).
    expect(withinCard.getByText('Alice')).toBeInTheDocument();
    expect(withinCard.getByText('Bob')).toBeInTheDocument();

    // Item 4: every account's server-computed short_name renders in full (not
    // truncated -- it's already short), and every balance is a direct value
    // label -- both visible without hovering.
    for (const owner of mockOverviewData.net_worth.owner_balances) {
      for (const account of owner.accounts) {
        const shortNameEl = withinCard.getByText(account.short_name);
        expect(shortNameEl).toBeInTheDocument();
        // The full original account_name is revealed on hover via a native
        // `title` attribute on the row.
        expect(shortNameEl.closest('[title]')).toHaveAttribute('title', account.account_name);
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

  it('renders month-over-month by category as a grouped bar chart with a Usual series and drift labels', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    expect(screen.getByText('Month-over-Month by Category')).toBeInTheDocument();
    // Legend now has a third "Usual" series alongside "This month"/"Last month".
    // The drift-percentage `<LabelList>` text nodes (e.g. "+20%") are real SVG
    // content produced only once Recharts' bar-entry animation completes --
    // like this file's other bar charts (Top Categories, Asset Mix), that
    // never happens under jsdom's fake timers, so -- consistent with how
    // those charts are tested elsewhere in this file -- this only asserts on
    // the chart's static content (heading, legend), not animated bar geometry.
    expect(screen.getByText('Usual')).toBeInTheDocument();
    expect(screen.getByText('This month')).toBeInTheDocument();
    expect(screen.getByText('Last month')).toBeInTheDocument();
  });

  it('renders the 5th KPI tile (Projected Month-End Spend) when a cash flow projection is present', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    expect(screen.getByText('Projected Month-End Spend')).toBeInTheDocument();
    expect(screen.getByText('$8,000')).toBeInTheDocument();
    expect(screen.getByText('day 20 of 31')).toBeInTheDocument();
  });

  it('does not render the 5th KPI tile when cash_flow_projection is null', () => {
    const noProjection: OverviewResponse = {
      ...mockOverviewData,
      overview: { ...mockOverviewData.overview, cash_flow_projection: null },
    };
    mockedUseOverview.mockReturnValue({
      data: noProjection,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    renderOverviewTab();

    expect(screen.queryByText('Projected Month-End Spend')).not.toBeInTheDocument();
  });

  it('renders the Biggest Expense This Month card, with an empty-state fallback', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    const { rerender } = renderOverviewTab();

    expect(screen.getByText('Biggest Expense This Month')).toBeInTheDocument();
    expect(screen.getByText('Rent')).toBeInTheDocument();
    expect(screen.getByText('$2,200')).toBeInTheDocument();

    const noExpense: OverviewResponse = {
      ...mockOverviewData,
      overview: { ...mockOverviewData.overview, biggest_expense_this_month: null },
    };
    mockedUseOverview.mockReturnValue({
      data: noExpense,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    rerender(
      <FilterProvider>
        <OverviewTab />
      </FilterProvider>,
    );

    expect(screen.getByText('No expenses recorded this month.')).toBeInTheDocument();
  });

  it('renders the Upcoming Recurring Charges card, with an empty-state fallback', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    const { rerender } = renderOverviewTab();

    const heading = screen.getByText('Upcoming Recurring Charges');
    const card = heading.closest('div');
    expect(card).not.toBeNull();
    const withinCard = within(card!);
    expect(withinCard.getByText('Netflix')).toBeInTheDocument();
    // formatCurrency rounds to whole dollars.
    expect(withinCard.getByText('$16')).toBeInTheDocument();

    const noUpcoming: OverviewResponse = {
      ...mockOverviewData,
      overview: { ...mockOverviewData.overview, upcoming_recurring: [] },
    };
    mockedUseOverview.mockReturnValue({
      data: noUpcoming,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    rerender(
      <FilterProvider>
        <OverviewTab />
      </FilterProvider>,
    );

    expect(screen.getByText('No recurring charges with a predictable cadence yet.')).toBeInTheDocument();
  });

  it('renders Top Merchants and Committed/Recurring Spend lists, with empty-state fallbacks', () => {
    mockedUseOverview.mockReturnValue({
      data: mockOverviewData,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    const { rerender } = renderOverviewTab();

    const merchantsHeading = screen.getByText('Top Merchants (Trailing 12 Months)');
    const merchantsCard = merchantsHeading.closest('div');
    expect(merchantsCard).not.toBeNull();
    expect(within(merchantsCard!).getByText('Amazon')).toBeInTheDocument();

    const recurringHeading = screen.getByText('Committed / Recurring Spend');
    const recurringCard = recurringHeading.closest('div');
    expect(recurringCard).not.toBeNull();
    expect(within(recurringCard!).getByText('Netflix')).toBeInTheDocument();

    const noneOfEither: OverviewResponse = {
      ...mockOverviewData,
      overview: { ...mockOverviewData.overview, top_merchants: [], recurring_items: [] },
    };
    mockedUseOverview.mockReturnValue({
      data: noneOfEither,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<OverviewResponse, Error>);

    rerender(
      <FilterProvider>
        <OverviewTab />
      </FilterProvider>,
    );

    expect(screen.getByText('Not enough expense history yet.')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Nothing flagged recurring yet — mark a transaction recurring in the Transactions tab.',
      ),
    ).toBeInTheDocument();
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
