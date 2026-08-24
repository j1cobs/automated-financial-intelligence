import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query';
import { BudgetTab } from './BudgetTab';
import type { BudgetResponse, CategoriesResponse, CashFlowResponse } from '../lib/types';

vi.mock('../lib/queries', () => ({
  useBudget: vi.fn(),
  useCategories: vi.fn(),
  useCashFlow: vi.fn(),
}));

vi.mock('../lib/mutations', () => ({
  useUpsertBudget: vi.fn(),
}));

// Recharts' ResponsiveContainer measures its parent via ResizeObserver, which
// jsdom doesn't implement, so charts never receive a nonzero size and render
// no children. Give the wrapped sparkline an explicit fixed size instead so
// chart internals actually render in tests.
vi.mock('recharts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('recharts')>();
  return {
    ...actual,
    ResponsiveContainer: ({
      children,
    }: {
      children: React.ReactElement<{ width?: number; height?: number }>;
    }) => React.cloneElement(children, { width: 200, height: 24 }),
  };
});

const { useBudget, useCategories, useCashFlow } = await import('../lib/queries');
const { useUpsertBudget } = await import('../lib/mutations');

type MockUseQueryResult<T> = Partial<UseQueryResult<T, Error>>;
type MockUseMutationResult = Partial<
  UseMutationResult<void, Error, { category: string; monthlyLimit: number }>
>;

function createMockQueryResult<T>(overrides: MockUseQueryResult<T>): UseQueryResult<T, Error> {
  return {
    data: undefined,
    isPending: false,
    error: null,
    status: 'success',
    fetchStatus: 'idle',
    isError: false,
    isSuccess: false,
    isStale: false,
    isFetching: false,
    isFetched: false,
    refetch: vi.fn(),
    dataUpdatedAt: 0,
    errorUpdatedAt: 0,
    ...overrides,
  } as unknown as UseQueryResult<T, Error>;
}

const createMockMutationResult = (
  overrides: MockUseMutationResult,
): UseMutationResult<void, Error, { category: string; monthlyLimit: number }> =>
  ({
    mutateAsync: vi.fn(),
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    isSuccess: false,
    error: null,
    data: undefined,
    status: 'idle',
    reset: vi.fn(),
    failureCount: 0,
    failureReason: null,
    variables: undefined,
    submittedAt: 0,
    ...overrides,
  }) as unknown as UseMutationResult<void, Error, { category: string; monthlyLimit: number }>;

const mockBudgetData: BudgetResponse = {
  month: 'August 2026',
  items: [
    {
      category: 'Groceries',
      spent: 250,
      limit: 400,
      pct: 0.625,
      is_over_budget: false,
      projected_eom: 350,
      is_current_month: true,
    },
    {
      category: 'Dining Out',
      spent: 500,
      limit: 300,
      pct: 1.667,
      is_over_budget: true,
      projected_eom: 700,
      is_current_month: true,
    },
    {
      category: 'Entertainment',
      spent: 50,
      limit: null,
      pct: null,
      is_over_budget: false,
      projected_eom: null,
      is_current_month: true,
    },
  ],
};

/** Rows render alphabetically (matching Streamlit's `sorted(...)`), not in API
 * response order, so tests target a category's own row rather than an index. */
function rowFor(category: string): HTMLElement {
  return screen.getByText(category).closest('div.border-l-4') as HTMLElement;
}

function renderWithQueryClient(component: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{component}</QueryClientProvider>);
}

/** Sets up useBudget/useUpsertBudget for a "happy path" render; categories and
 * cash-flow default to empty unless the test overrides them separately. */
function mockHappyPath(budget: BudgetResponse = mockBudgetData) {
  vi.mocked(useBudget).mockReturnValue(
    createMockQueryResult<BudgetResponse>({
      data: budget,
      isPending: false,
      status: 'success',
      isSuccess: true,
      isFetched: true,
      dataUpdatedAt: Date.now(),
    }),
  );
  vi.mocked(useUpsertBudget).mockReturnValue(createMockMutationResult({}));
}

describe('BudgetTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Defaults: no extra canonical categories, no trend history. Individual
    // tests override these when they need to.
    vi.mocked(useCategories).mockReturnValue(
      createMockQueryResult<CategoriesResponse>({
        data: { categories: [] },
        isSuccess: true,
        isFetched: true,
      }),
    );
    vi.mocked(useCashFlow).mockReturnValue(
      createMockQueryResult<CashFlowResponse>({ data: undefined, isSuccess: false }),
    );
  });

  it('renders loading state', () => {
    vi.mocked(useBudget).mockReturnValue(
      createMockQueryResult<BudgetResponse>({
        isPending: true,
        status: 'pending',
        fetchStatus: 'fetching',
        isFetching: true,
      }),
    );

    renderWithQueryClient(<BudgetTab />);

    expect(screen.getByText('Budget')).toBeInTheDocument();
    expect(screen.getByText('Loading budget data...')).toBeInTheDocument();
  });

  it('renders error state', () => {
    vi.mocked(useBudget).mockReturnValue(
      createMockQueryResult<BudgetResponse>({
        isPending: false,
        error: new Error('Failed to fetch'),
        status: 'error',
        isError: true,
        isFetched: true,
        errorUpdatedAt: Date.now(),
      }),
    );

    renderWithQueryClient(<BudgetTab />);

    expect(screen.getByText('Budget')).toBeInTheDocument();
    expect(screen.getByText('Failed to load budget data. Please try again.')).toBeInTheDocument();
  });

  it('renders budget items with spend and limit information', () => {
    mockHappyPath();

    renderWithQueryClient(<BudgetTab />);

    expect(screen.getByText('August 2026')).toBeInTheDocument();
    expect(screen.getByText('Groceries')).toBeInTheDocument();
    expect(screen.getByText('Dining Out')).toBeInTheDocument();
    expect(screen.getByText('Entertainment')).toBeInTheDocument();

    // Check that spent and limit are displayed for Groceries
    const groceriesContainer = screen.getByText('Groceries').closest('div.min-w-0');
    expect(groceriesContainer).toHaveTextContent('$250.00');
    expect(groceriesContainer).toHaveTextContent('$400.00');

    // Check progress percentage (62.5% rounds to 63%)
    expect(screen.getByText('— 63% of limit')).toBeInTheDocument();
    // 166.7% rounds to 167%
    expect(screen.getByText('— 167% of limit')).toBeInTheDocument();

    // Entertainment has spend but no limit -- Streamlit's "no budget set" path.
    const entertainmentContainer = screen.getByText('Entertainment').closest('div.min-w-0');
    expect(entertainmentContainer).toHaveTextContent('$50.00');
    expect(entertainmentContainer).toHaveTextContent('no budget set');
  });

  it('shows the projection only for the current-month period', () => {
    const historical: BudgetResponse = {
      month: '2026-06',
      items: [
        {
          category: 'Travel',
          spent: 900,
          limit: 1000,
          pct: 0.9,
          is_over_budget: false,
          projected_eom: 1200, // API happens to compute this, but it must not render
          is_current_month: false,
        },
      ],
    };
    mockHappyPath(historical);

    renderWithQueryClient(<BudgetTab />);

    expect(screen.getByText('Travel')).toBeInTheDocument();
    expect(screen.queryByText(/Projected EOM/)).not.toBeInTheDocument();
  });

  it('shows the projection for a current-month category', () => {
    mockHappyPath();

    renderWithQueryClient(<BudgetTab />);

    const groceriesContainer = screen.getByText('Groceries').closest('div.min-w-0');
    expect(groceriesContainer).toHaveTextContent('Projected EOM: $350.00');

    // Entertainment is current-month but has no limit and (per build_budget)
    // no projected_eom is computed unless is_current_month -- it still is
    // here, so the projection should show once a limit exists; without one
    // Streamlit shows "Actual" only for historical periods, so nothing extra
    // is asserted for Entertainment beyond the no-budget-set text above.
  });

  it('renders over-budget rows distinguished by more than colour alone', () => {
    mockHappyPath();

    renderWithQueryClient(<BudgetTab />);

    // A glyph + text label must accompany the status, not just a colour class.
    expect(screen.getByText('Over budget')).toBeInTheDocument();
    expect(screen.getByText('On track')).toBeInTheDocument();
    expect(screen.getByText('No budget set')).toBeInTheDocument();

    const diningOutRow = screen.getByText('Dining Out').closest('div.border-l-4');
    expect(diningOutRow).not.toBeNull();
    expect(diningOutRow).toHaveTextContent('Over budget');
  });

  it('offers a category with no spend and no existing limit in the editor', async () => {
    vi.mocked(useCategories).mockReturnValue(
      createMockQueryResult<CategoriesResponse>({
        data: { categories: ['Groceries', 'Dining Out', 'Entertainment', 'Subscriptions'] },
        isSuccess: true,
        isFetched: true,
      }),
    );
    mockHappyPath();

    renderWithQueryClient(<BudgetTab />);

    // "Subscriptions" has no spend and no budget row at all in the API
    // response -- it only exists in the canonical category list -- yet it
    // must still be listed and editable.
    expect(screen.getByText('Subscriptions')).toBeInTheDocument();

    const subscriptionsRow = rowFor('Subscriptions');
    expect(within(subscriptionsRow).getByText('No budget set')).toBeInTheDocument();
    const editButton = within(subscriptionsRow).getByText('Edit');
    await userEvent.click(editButton);

    expect(within(subscriptionsRow).getByDisplayValue('0')).toBeInTheDocument();
  });

  it('opens edit form when Edit button is clicked', async () => {
    mockHappyPath();

    renderWithQueryClient(<BudgetTab />);

    await userEvent.click(within(rowFor('Groceries')).getByText('Edit'));

    // Should show the edit form with the current limit
    expect(screen.getByDisplayValue('400')).toBeInTheDocument();
    expect(screen.getByText('Save')).toBeInTheDocument();
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  it('calls useUpsertBudget mutation with the right category and value when Save is clicked', async () => {
    const mockMutateAsync = vi.fn().mockResolvedValue(undefined);
    mockHappyPath();
    vi.mocked(useUpsertBudget).mockReturnValue(
      createMockMutationResult({
        mutateAsync: mockMutateAsync,
      }),
    );

    renderWithQueryClient(<BudgetTab />);

    await userEvent.click(within(rowFor('Groceries')).getByText('Edit'));

    const input = screen.getByDisplayValue('400');
    await userEvent.clear(input);
    await userEvent.type(input, '500');

    const saveButton = screen.getByText('Save');
    await userEvent.click(saveButton);

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        category: 'Groceries',
        monthlyLimit: 500,
      });
    });
  });

  it('closes edit form when Cancel is clicked', async () => {
    mockHappyPath();

    renderWithQueryClient(<BudgetTab />);

    await userEvent.click(within(rowFor('Groceries')).getByText('Edit'));

    expect(screen.getByDisplayValue('400')).toBeInTheDocument();

    const cancelButton = screen.getByText('Cancel');
    await userEvent.click(cancelButton);

    // After cancel, edit form should be closed and edit button should reappear
    await waitFor(() => {
      expect(screen.queryByDisplayValue('400')).not.toBeInTheDocument();
      expect(screen.getAllByText('Edit').length).toBeGreaterThan(0);
    });
  });

  it('renders empty state when no budget items and no canonical categories', () => {
    mockHappyPath({ month: 'August 2026', items: [] });

    renderWithQueryClient(<BudgetTab />);

    expect(screen.getByText('No budget data available.')).toBeInTheDocument();
  });

  it('renders a trend sparkline when category_distribution history exists', () => {
    mockHappyPath();
    vi.mocked(useCashFlow).mockReturnValue(
      createMockQueryResult<CashFlowResponse>({
        data: {
          income: 0,
          expenses: 0,
          net_flow: 0,
          transfer_count: 0,
          flagged_count: 0,
          savings_rate: 0,
          month_over_month: [],
          weekly_trend: [],
          rolling_30d_spend: [],
          monthly_net_by_owner: [],
          category_distribution: [
            { month: '2026-04', category: 'Groceries', amount: 200 },
            { month: '2026-05', category: 'Groceries', amount: 220 },
            { month: '2026-06', category: 'Groceries', amount: 240 },
          ],
        },
        isSuccess: true,
        isFetched: true,
      }),
    );

    const { container } = renderWithQueryClient(<BudgetTab />);

    expect(container.querySelector('.recharts-line')).not.toBeNull();
    expect(screen.queryAllByText('No trend').length).toBeGreaterThan(0); // other rows still lack history
  });
});
