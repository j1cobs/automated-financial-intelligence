import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MetricTile } from './MetricTile';
import type { MetricSummary } from '../lib/types';

// Recharts' ResponsiveContainer measures its parent via ResizeObserver, which
// jsdom doesn't implement, so the sparkline never receives a nonzero size and
// renders no children. Give it a fixed size instead, mirroring the pattern in
// OverviewTab.test.tsx / CashFlowTab.test.tsx.
vi.mock('recharts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('recharts')>();
  return {
    ...actual,
    ResponsiveContainer: ({
      children,
    }: {
      children: React.ReactElement<{ width?: number; height?: number }>;
    }) => React.cloneElement(children, { width: 80, height: 32 }),
  };
});

function summary(overrides: Partial<MetricSummary> = {}): MetricSummary {
  return {
    key: 'avg_monthly_income',
    value: 5000,
    baseline: 4000,
    delta_pct: 0.25,
    baseline_months: 3,
    sparkline: [3800, 4200, 5000],
    ...overrides,
  };
}

describe('MetricTile', () => {
  it('renders the label from metricInfo and the formatted value', () => {
    render(<MetricTile metricKey="net_worth" value={125000} />);

    expect(screen.getByText('Net Worth')).toBeInTheDocument();
    expect(screen.getByText('$125,000')).toBeInTheDocument();
  });

  it('renders a percent-formatted value', () => {
    render(<MetricTile metricKey="savings_rate" value={0.6} format="percent" />);

    expect(screen.getByText('60.0%')).toBeInTheDocument();
  });

  it('renders no delta badge or sparkline when no metric context is passed', () => {
    const { container } = render(<MetricTile metricKey="flagged_count" value={3} format="number" />);

    expect(container.querySelector('[data-testid="metric-sparkline"]')).not.toBeInTheDocument();
  });

  it('renders the delta badge with a glyph AND a text label, not colour alone', () => {
    // avg_monthly_income is polarity 'normal': a positive delta is good.
    render(<MetricTile metricKey="avg_monthly_income" value={5000} metric={summary()} />);

    expect(screen.getByText('↑')).toBeInTheDocument();
    expect(screen.getByText('up (better)')).toBeInTheDocument();
  });

  it('flips good/bad for an inverse-polarity metric (expenses up is bad)', () => {
    const expenseUp = summary({ key: 'avg_monthly_expense', value: 5000, baseline: 4000, delta_pct: 0.25 });
    render(<MetricTile metricKey="avg_monthly_expense" value={5000} metric={expenseUp} />);

    // Same positive delta as the income case, opposite word: worse, not better.
    expect(screen.getByText('↑')).toBeInTheDocument();
    expect(screen.getByText('up (worse)')).toBeInTheDocument();
  });

  it('renders the baseline comparison text derived from delta_pct and baseline_months', () => {
    render(<MetricTile metricKey="avg_monthly_income" value={5000} metric={summary()} />);

    expect(screen.getByText('25% above your 3-month average')).toBeInTheDocument();
  });

  it('renders no comparison when baseline is null', () => {
    const noBaseline = summary({ baseline: null, delta_pct: null, baseline_months: 0 });
    render(<MetricTile metricKey="avg_monthly_income" value={5000} metric={noBaseline} />);

    expect(screen.queryByText(/vs your|above your|below your|at your/)).not.toBeInTheDocument();
  });

  it('renders a sparkline when the metric has 2+ points, and none below that', () => {
    const { container: withSpark } = render(
      <MetricTile metricKey="avg_monthly_income" value={5000} metric={summary()} />,
    );
    expect(withSpark.querySelector('[data-testid="metric-sparkline"]')).toBeInTheDocument();

    const { container: withoutSpark } = render(
      <MetricTile metricKey="avg_monthly_income" value={5000} metric={summary({ sparkline: [5000] })} />,
    );
    expect(withoutSpark.querySelector('[data-testid="metric-sparkline"]')).not.toBeInTheDocument();
  });

  it('opens the info tooltip via keyboard (Tab + Enter) and it carries the registry content', async () => {
    const user = userEvent.setup();
    render(<MetricTile metricKey="net_worth" value={125000} />);

    const trigger = screen.getByRole('button', { name: 'More about Net Worth' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');

    await user.tab();
    expect(trigger).toHaveFocus();
    await user.keyboard('{Enter}');

    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    const tooltip = screen.getByRole('tooltip');
    expect(
      within(tooltip).getByText("What you'd have left if you settled every account today."),
    ).toBeInTheDocument();
    expect(within(tooltip).getByText(/total assets − total liabilities/)).toBeInTheDocument();
  });

  it('closes the tooltip on Escape and returns focus to the trigger', () => {
    render(<MetricTile metricKey="net_worth" value={125000} />);

    const trigger = screen.getByRole('button', { name: 'More about Net Worth' });
    fireEvent.click(trigger);
    expect(screen.getByRole('tooltip')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(document.activeElement).toBe(trigger);
  });

  it('lists the excludes for a metric that has them', () => {
    render(<MetricTile metricKey="savings_rate" value={0.5} format="percent" />);

    fireEvent.click(screen.getByRole('button', { name: 'More about Savings Rate' }));

    const tooltip = screen.getByRole('tooltip');
    expect(within(tooltip).getByText('Internal transfers between your own accounts')).toBeInTheDocument();
    expect(within(tooltip).getByText('Transactions you flagged as duplicates')).toBeInTheDocument();
  });

  it('accepts an onDrillDown prop without rendering any drill-down UI', () => {
    const onDrillDown = () => {};
    const { container } = render(
      <MetricTile metricKey="net_worth" value={125000} onDrillDown={onDrillDown} />,
    );

    // No button/link beyond the info-tooltip trigger exists on the tile.
    const buttons = container.querySelectorAll('button');
    expect(buttons.length).toBe(1);
    expect(buttons[0]).toHaveAttribute('aria-label', 'More about Net Worth');
  });

  it('renders a sublabel caption when provided', () => {
    render(<MetricTile metricKey="avg_monthly_income" value={5000} sublabel="avg of 3 complete months" />);

    expect(screen.getByText('avg of 3 complete months')).toBeInTheDocument();
  });
});
