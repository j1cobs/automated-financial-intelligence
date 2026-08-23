import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query';
import { BudgetTab } from './BudgetTab';
import type { BudgetResponse } from '../lib/types';

vi.mock('../lib/queries', () => ({
  useBudget: vi.fn(),
}));

vi.mock('../lib/mutations', () => ({
  useUpsertBudget: vi.fn(),
}));

const { useBudget } = await import('../lib/queries');
const { useUpsertBudget } = await import('../lib/mutations');

type MockUseQueryResult = Partial<UseQueryResult<BudgetResponse, Error>>;
type MockUseMutationResult = Partial<
  UseMutationResult<void, Error, { category: string; monthlyLimit: number }>
>;

const createMockQueryResult = (overrides: MockUseQueryResult): UseQueryResult<BudgetResponse, Error> =>
  ({
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
  }) as unknown as UseQueryResult<BudgetResponse, Error>;

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

function renderWithQueryClient(component: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{component}</QueryClientProvider>);
}

describe('BudgetTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state', () => {
    const mockUseBudget = vi.mocked(useBudget);
    mockUseBudget.mockReturnValue(
      createMockQueryResult({
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
    const mockUseBudget = vi.mocked(useBudget);
    mockUseBudget.mockReturnValue(
      createMockQueryResult({
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
    const mockUseBudget = vi.mocked(useBudget);
    const mockUpsertBudget = vi.mocked(useUpsertBudget);

    mockUseBudget.mockReturnValue(
      createMockQueryResult({
        data: mockBudgetData,
        isPending: false,
        status: 'success',
        isSuccess: true,
        isFetched: true,
        dataUpdatedAt: Date.now(),
      }),
    );

    mockUpsertBudget.mockReturnValue(createMockMutationResult({}));

    renderWithQueryClient(<BudgetTab />);

    expect(screen.getByText('August 2026')).toBeInTheDocument();
    expect(screen.getByText('Groceries')).toBeInTheDocument();
    expect(screen.getByText('Dining Out')).toBeInTheDocument();
    expect(screen.getByText('Entertainment')).toBeInTheDocument();

    // Check that spent and limit are displayed for Groceries
    const groceriesContainer = screen.getByText('Groceries').closest('div');
    expect(groceriesContainer).toHaveTextContent('$250.00');
    expect(groceriesContainer).toHaveTextContent('$400.00');

    // Check progress percentage (62.5% rounds to 63%)
    expect(screen.getByText('63% of limit')).toBeInTheDocument();
    // 166.7% rounds to 167%
    expect(screen.getByText('167% of limit')).toBeInTheDocument();
  });

  it('renders items with over-budget styling', () => {
    const mockUseBudget = vi.mocked(useBudget);
    const mockUpsertBudget = vi.mocked(useUpsertBudget);

    mockUseBudget.mockReturnValue(
      createMockQueryResult({
        data: mockBudgetData,
        isPending: false,
        status: 'success',
        isSuccess: true,
        isFetched: true,
        dataUpdatedAt: Date.now(),
      }),
    );

    mockUpsertBudget.mockReturnValue(createMockMutationResult({}));

    renderWithQueryClient(<BudgetTab />);

    // Find the Dining Out row (which is over budget)
    const diningOutElement = screen.getByText('Dining Out');
    // Navigate up to find the budget item container with the red styling
    let container = diningOutElement.closest('div') as HTMLDivElement | null;
    while (container && !container.className.includes('border')) {
      container = container.parentElement as HTMLDivElement | null;
    }
    expect(container).toHaveClass('bg-red-50');
    expect(container).toHaveClass('border-red-200');
  });

  it('opens edit form when Edit button is clicked', async () => {
    const mockUseBudget = vi.mocked(useBudget);
    const mockUpsertBudget = vi.mocked(useUpsertBudget);

    mockUseBudget.mockReturnValue(
      createMockQueryResult({
        data: mockBudgetData,
        isPending: false,
        status: 'success',
        isSuccess: true,
        isFetched: true,
        dataUpdatedAt: Date.now(),
      }),
    );

    mockUpsertBudget.mockReturnValue(createMockMutationResult({}));

    renderWithQueryClient(<BudgetTab />);

    const editButtons = screen.getAllByText('Edit');
    await userEvent.click(editButtons[0]);

    // Should show the edit form with the current limit
    expect(screen.getByDisplayValue('400')).toBeInTheDocument();
    expect(screen.getByText('Save')).toBeInTheDocument();
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  it('calls useUpsertBudget mutation when Save is clicked', async () => {
    const mockUseBudget = vi.mocked(useBudget);
    const mockUpsertBudget = vi.mocked(useUpsertBudget);
    const mockMutateAsync = vi.fn().mockResolvedValue(undefined);

    mockUseBudget.mockReturnValue(
      createMockQueryResult({
        data: mockBudgetData,
        isPending: false,
        status: 'success',
        isSuccess: true,
        isFetched: true,
        dataUpdatedAt: Date.now(),
      }),
    );

    mockUpsertBudget.mockReturnValue(
      createMockMutationResult({
        mutateAsync: mockMutateAsync,
      }),
    );

    renderWithQueryClient(<BudgetTab />);

    const editButtons = screen.getAllByText('Edit');
    await userEvent.click(editButtons[0]);

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
    const mockUseBudget = vi.mocked(useBudget);
    const mockUpsertBudget = vi.mocked(useUpsertBudget);

    mockUseBudget.mockReturnValue(
      createMockQueryResult({
        data: mockBudgetData,
        isPending: false,
        status: 'success',
        isSuccess: true,
        isFetched: true,
        dataUpdatedAt: Date.now(),
      }),
    );

    mockUpsertBudget.mockReturnValue(createMockMutationResult({}));

    renderWithQueryClient(<BudgetTab />);

    const editButtons = screen.getAllByText('Edit');
    await userEvent.click(editButtons[0]);

    expect(screen.getByDisplayValue('400')).toBeInTheDocument();

    const cancelButton = screen.getByText('Cancel');
    await userEvent.click(cancelButton);

    // After cancel, edit form should be closed and edit button should reappear
    await waitFor(() => {
      expect(screen.queryByDisplayValue('400')).not.toBeInTheDocument();
      expect(screen.getAllByText('Edit').length).toBeGreaterThan(0);
    });
  });

  it('renders empty state when no budget items', () => {
    const mockUseBudget = vi.mocked(useBudget);
    const mockUpsertBudget = vi.mocked(useUpsertBudget);

    mockUseBudget.mockReturnValue(
      createMockQueryResult({
        data: { month: 'August 2026', items: [] },
        isPending: false,
        status: 'success',
        isSuccess: true,
        isFetched: true,
        dataUpdatedAt: Date.now(),
      }),
    );

    mockUpsertBudget.mockReturnValue(createMockMutationResult({}));

    renderWithQueryClient(<BudgetTab />);

    expect(screen.getByText('No budget data available.')).toBeInTheDocument();
  });
});
