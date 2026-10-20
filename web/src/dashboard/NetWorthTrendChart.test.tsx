import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NetWorthTrendChart } from './NetWorthTrendChart';
import type { NetWorthTrendDailyItem, NetWorthTrendMonthlyItem } from '../lib/types';

// Recharts' ResponsiveContainer measures its parent via ResizeObserver, which
// jsdom doesn't implement, so charts never receive a nonzero size and render
// no children. Give it a fixed size instead, mirroring the pattern in
// OverviewTab.test.tsx / TransactionsTab.test.tsx.
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

const dailyData: NetWorthTrendDailyItem[] = [
  { date: '2026-08-20', net_worth: 10000, assets: 15000, liabilities: 5000, liquid_cash: 4000 },
  { date: '2026-08-21', net_worth: 10200, assets: 15200, liabilities: 5000, liquid_cash: 4100 },
];

const monthlyData: NetWorthTrendMonthlyItem[] = [
  {
    month: '2026-06',
    net_worth: 9000,
    savings_rate: 0.2,
    credit_utilization_pct: 0.3,
    emergency_fund_months: 4.4,
  },
  {
    month: '2026-07',
    net_worth: 9500,
    savings_rate: 0.25,
    credit_utilization_pct: 0.28,
    emergency_fund_months: 4.6,
  },
  {
    month: '2026-08',
    net_worth: 10000,
    savings_rate: 0.22,
    credit_utilization_pct: null,
    emergency_fund_months: 4.8,
  },
];

describe('NetWorthTrendChart', () => {
  it('defaults to the Net Worth tab and renders the net worth line only', () => {
    render(<NetWorthTrendChart daily={dailyData} monthly={monthlyData} netWorthMomDelta={500} />);

    expect(screen.getByRole('button', { name: 'Net Worth' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: 'Daily' })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('button', { name: 'Rates' })).not.toHaveAttribute('aria-current');
    // No legend on this single-line tab, but the mom-delta caption confirms it rendered.
    expect(screen.getByText(/since last month/)).toBeInTheDocument();
  });

  it('hides the mom-delta caption when netWorthMomDelta is null', () => {
    render(<NetWorthTrendChart daily={dailyData} monthly={monthlyData} netWorthMomDelta={null} />);
    expect(screen.queryByText(/since last month/)).not.toBeInTheDocument();
  });

  it('switches to the Daily tab and renders its four series in the legend', async () => {
    const user = userEvent.setup();
    render(<NetWorthTrendChart daily={dailyData} monthly={monthlyData} netWorthMomDelta={500} />);

    await user.click(screen.getByRole('button', { name: 'Daily' }));

    expect(screen.getByRole('button', { name: 'Daily' })).toHaveAttribute('aria-current', 'page');
    // 'Net Worth' also matches the (now-inactive) tab button, so scope to the legend.
    expect(screen.getByText('Net Worth', { selector: '.recharts-legend-item-text' })).toBeInTheDocument();
    expect(screen.getByText('Total Assets')).toBeInTheDocument();
    expect(screen.getByText('Total Liabilities')).toBeInTheDocument();
    expect(screen.getByText('Liquid Cash')).toBeInTheDocument();
    // No mom-delta caption on the Daily tab.
    expect(screen.queryByText(/since last month/)).not.toBeInTheDocument();
  });

  it('switches to the Rates tab and renders savings rate + credit utilization in the legend', async () => {
    const user = userEvent.setup();
    render(<NetWorthTrendChart daily={dailyData} monthly={monthlyData} netWorthMomDelta={500} />);

    await user.click(screen.getByRole('button', { name: 'Rates' }));

    expect(screen.getByRole('button', { name: 'Rates' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByText('Savings Rate')).toBeInTheDocument();
    expect(screen.getByText('Credit Utilization %')).toBeInTheDocument();
    // Emergency Fund Months is intentionally dropped from this chart entirely
    // (it has its own live-value card elsewhere on the Overview tab).
    expect(screen.queryByText('Emergency Fund Months')).not.toBeInTheDocument();
    // No mom-delta caption on the Rates tab.
    expect(screen.queryByText(/since last month/)).not.toBeInTheDocument();
  });

  it('clicking a legend entry on the Rates tab does not throw and keeps the line in the legend', async () => {
    const user = userEvent.setup();
    render(<NetWorthTrendChart daily={dailyData} monthly={monthlyData} netWorthMomDelta={500} />);

    await user.click(screen.getByRole('button', { name: 'Rates' }));
    const savingsRateLegendItem = screen.getByText('Savings Rate');
    await user.click(savingsRateLegendItem);

    // The line stays mounted (still listed in the legend) even after toggling.
    expect(screen.getByText('Savings Rate')).toBeInTheDocument();
  });

  it('renders a graceful empty state for an empty monthly array on the Net Worth tab', () => {
    render(<NetWorthTrendChart daily={dailyData} monthly={[]} netWorthMomDelta={null} />);
    expect(screen.getByText(/Not enough monthly history yet/)).toBeInTheDocument();
  });

  it('renders a graceful empty state for an empty monthly array on the Rates tab', async () => {
    const user = userEvent.setup();
    render(<NetWorthTrendChart daily={dailyData} monthly={[]} netWorthMomDelta={null} />);

    await user.click(screen.getByRole('button', { name: 'Rates' }));
    expect(screen.getByText(/Not enough monthly history yet/)).toBeInTheDocument();
  });

  it('renders a graceful empty state for an empty daily array on the Daily tab', async () => {
    const user = userEvent.setup();
    render(<NetWorthTrendChart daily={[]} monthly={monthlyData} netWorthMomDelta={null} />);

    await user.click(screen.getByRole('button', { name: 'Daily' }));

    expect(screen.getByText(/History starts the day balance tracking shipped/)).toBeInTheDocument();
  });

  it('renders both empty states gracefully when both arrays are empty', async () => {
    const user = userEvent.setup();
    render(<NetWorthTrendChart daily={[]} monthly={[]} netWorthMomDelta={null} />);

    expect(screen.getByText(/Not enough monthly history yet/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Daily' }));
    expect(screen.getByText(/History starts the day balance tracking shipped/)).toBeInTheDocument();
  });
});
