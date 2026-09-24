import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen } from '@testing-library/react';
import { ForecastChart } from './ForecastChart';
import type { ForecastResponse } from '../lib/types';

vi.mock('../lib/queries', () => ({
  useForecast: vi.fn(),
}));

// Recharts measures its parent via ResizeObserver, which jsdom lacks, so the
// chart would otherwise render no children.
vi.mock('recharts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('recharts')>();
  return {
    ...actual,
    ResponsiveContainer: ({
      children,
    }: {
      children: React.ReactElement<{ width?: number; height?: number }>;
    }) => React.cloneElement(children, { width: 800, height: 300 }),
  };
});

import { useForecast } from '../lib/queries';

const mockedUseForecast = vi.mocked(useForecast);

function response(overrides: Partial<ForecastResponse> = {}): ForecastResponse {
  return {
    rows: [
      { month: '2026-10', projected_balance: 3000, budget_balance: 3400, income: 3000, expenses: 1000 },
      { month: '2026-11', projected_balance: 5000, budget_balance: 5800, income: 3000, expenses: 1000 },
    ],
    has_enough_history: true,
    has_recurring_data: true,
    months_of_history: 4,
    starting_balance: 1000,
    ...overrides,
  };
}

function mockForecast(data: ForecastResponse | undefined, isPending = false) {
  mockedUseForecast.mockReturnValue({ data, isPending } as unknown as ReturnType<typeof useForecast>);
}

describe('ForecastChart', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders nothing while loading', () => {
    mockForecast(undefined, true);
    const { container } = render(<ForecastChart />);
    expect(container).toBeEmptyDOMElement();
  });

  // Below three complete months a median is a guess. Saying so beats drawing
  // a confident-looking line built on two months of data.
  it('says it is still building history instead of projecting', () => {
    mockForecast(response({ has_enough_history: false, months_of_history: 2, rows: [] }));
    render(<ForecastChart />);

    expect(screen.getByText(/building history/i)).toBeInTheDocument();
    expect(screen.getByText(/2 complete months/)).toBeInTheDocument();
    expect(screen.getByText(/at least three/)).toBeInTheDocument();
  });

  it('uses the singular for one month of history', () => {
    mockForecast(response({ has_enough_history: false, months_of_history: 1, rows: [] }));
    render(<ForecastChart />);
    expect(screen.getByText(/1 complete month\b/)).toBeInTheDocument();
  });

  it('renders both series with a legend once there is enough history', () => {
    mockForecast(response());
    render(<ForecastChart />);

    // Two series means a legend is always present -- identity is never
    // carried by colour alone.
    expect(screen.getByText('Projected')).toBeInTheDocument();
    expect(screen.getByText('If you hit every cap')).toBeInTheDocument();
  });

  it('shows the starting balance the projection runs from', () => {
    mockForecast(response({ starting_balance: 1234 }));
    render(<ForecastChart />);
    expect(screen.getByText(/\$1,234 on hand/)).toBeInTheDocument();
  });

  it('says when there are no recurring charges behind the projection', () => {
    mockForecast(response({ has_recurring_data: false }));
    render(<ForecastChart />);
    expect(screen.getByText(/trailing averages alone/i)).toBeInTheDocument();
  });

  it('does not caveat recurring data when streams exist', () => {
    mockForecast(response({ has_recurring_data: true }));
    render(<ForecastChart />);
    expect(screen.queryByText(/trailing averages alone/i)).not.toBeInTheDocument();
  });

  it('draws the budget line dashed, so the two are tellable apart without colour', () => {
    mockForecast(response());
    const { container } = render(<ForecastChart />);

    // Exactly the budget line is dashed. Animation is off, so Recharts is not
    // driving stroke-dasharray itself and this reflects the real encoding.
    const dashed = container.querySelectorAll('path[stroke-dasharray="5 4"]');
    expect(dashed.length).toBe(1);
  });
});
