import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  QueryClient,
  QueryClientProvider,
  type UseQueryResult,
  type UseMutationResult,
} from '@tanstack/react-query';
import { TransactionsTab } from './TransactionsTab';
import type { LedgerResponse, AnomaliesResponse, CategoriesResponse } from '../lib/types';

// Mock the queries and mutations
vi.mock('../lib/queries', () => ({
  useLedger: vi.fn(),
  useAnomalies: vi.fn(),
  useCategories: vi.fn(),
}));

vi.mock('../lib/mutations', () => ({
  useUpdateCategory: vi.fn(),
  useUpdateRecurring: vi.fn(),
  useUpdateDuplicate: vi.fn(),
}));

import { useLedger, useAnomalies, useCategories } from '../lib/queries';
import { useUpdateCategory, useUpdateRecurring, useUpdateDuplicate } from '../lib/mutations';

const mockedUseLedger = vi.mocked(useLedger);
const mockedUseAnomalies = vi.mocked(useAnomalies);
const mockedUseCategories = vi.mocked(useCategories);
const mockedUseUpdateCategory = vi.mocked(useUpdateCategory);
const mockedUseUpdateRecurring = vi.mocked(useUpdateRecurring);
const mockedUseUpdateDuplicate = vi.mocked(useUpdateDuplicate);

function renderComponent() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <TransactionsTab />
    </QueryClientProvider>,
  );
}

// Helper to create mock query result objects with proper types
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

function mockMutation<TVariables>(
  mutateAsync: (vars: TVariables) => Promise<void>,
): UseMutationResult<void, Error, TVariables> {
  return {
    mutate: vi.fn(),
    mutateAsync,
    status: 'idle',
    isPending: false,
    isSuccess: false,
    isError: false,
    data: undefined,
    error: null,
    failureCount: 0,
    failureReason: null,
    reset: vi.fn(),
    variables: undefined,
    context: undefined,
  } as unknown as UseMutationResult<void, Error, TVariables>;
}

describe('TransactionsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Ledger loading and error states', () => {
    it('renders loading state for ledger', () => {
      mockedUseLedger.mockReturnValue(mockQueryLoading<LedgerResponse>());
      mockedUseAnomalies.mockReturnValue(mockQueryLoading<AnomaliesResponse>());
      mockedUseCategories.mockReturnValue(mockQueryLoading<CategoriesResponse>());

      renderComponent();

      expect(screen.getByText(/loading transactions/i)).toBeInTheDocument();
    });

    it('renders error state for ledger', () => {
      mockedUseLedger.mockReturnValue(mockQueryError<LedgerResponse>());
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));

      renderComponent();

      expect(screen.getByText(/failed to load transactions/i)).toBeInTheDocument();
    });
  });

  describe('Anomalies loading and error states', () => {
    it('renders loading state for anomalies', () => {
      mockedUseLedger.mockReturnValue(mockQuerySuccess({ transactions: [] }));
      mockedUseAnomalies.mockReturnValue(mockQueryLoading<AnomaliesResponse>());
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));

      renderComponent();

      expect(screen.getByText(/loading anomalies/i)).toBeInTheDocument();
    });

    it('renders error state for anomalies', () => {
      mockedUseLedger.mockReturnValue(mockQuerySuccess({ transactions: [] }));
      mockedUseAnomalies.mockReturnValue(mockQueryError<AnomaliesResponse>());
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));

      renderComponent();

      expect(screen.getByText(/failed to load anomalies/i)).toBeInTheDocument();
    });
  });

  describe('Ledger rendering', () => {
    it('renders ledger table with transactions', () => {
      const mockLedgerData: LedgerResponse = {
        transactions: [
          {
            hash: 'tx-1',
            date: '2024-01-15',
            account_name: 'Checking',
            owner_name: 'John Doe',
            description: 'Grocery Store',
            amount: -50.25,
            category: 'Groceries',
            is_recurring: false,
            is_duplicate: false,
          },
          {
            hash: 'tx-2',
            date: '2024-01-14',
            account_name: 'Credit Card',
            owner_name: null,
            description: 'Gas Station',
            amount: -40.0,
            category: null,
            is_recurring: true,
            is_duplicate: false,
          },
        ],
      };

      mockedUseLedger.mockReturnValue(mockQuerySuccess(mockLedgerData));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(
        mockQuerySuccess({ categories: ['Groceries', 'Gas', 'Utilities'] }),
      );
      mockedUseUpdateCategory.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));
      mockedUseUpdateRecurring.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));
      mockedUseUpdateDuplicate.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));

      renderComponent();

      expect(screen.getByText('Grocery Store')).toBeInTheDocument();
      expect(screen.getByText('Gas Station')).toBeInTheDocument();
      expect(screen.getByText('Groceries')).toBeInTheDocument();
      expect(screen.getByText('John Doe')).toBeInTheDocument();
    });

    it('renders empty ledger message when no transactions', () => {
      mockedUseLedger.mockReturnValue(mockQuerySuccess({ transactions: [] }));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));

      renderComponent();

      expect(screen.getByText(/no transactions found/i)).toBeInTheDocument();
    });
  });

  describe('Anomalies rendering', () => {
    it('renders anomalies table with outlier transactions', () => {
      const mockAnomaliesData: AnomaliesResponse = {
        anomalies: [
          {
            date: '2024-01-20',
            account_name: 'Savings',
            owner_name: 'Jane Doe',
            description: 'Large Withdrawal',
            amount: -5000.0,
            category: 'Withdrawal',
            outlier_score: 0.95,
          },
        ],
      };

      mockedUseLedger.mockReturnValue(mockQuerySuccess({ transactions: [] }));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess(mockAnomaliesData));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));

      renderComponent();

      expect(screen.getByText('Large Withdrawal')).toBeInTheDocument();
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
      expect(screen.getByText('0.950')).toBeInTheDocument();
    });

    it('renders empty anomalies message when none detected', () => {
      mockedUseLedger.mockReturnValue(mockQuerySuccess({ transactions: [] }));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));

      renderComponent();

      expect(screen.getByText(/no anomalies detected/i)).toBeInTheDocument();
    });
  });

  describe('Category editing', () => {
    it('calls useUpdateCategory mutation when category is changed', async () => {
      const user = userEvent.setup();
      const mockMutateAsync = vi.fn().mockResolvedValue(undefined);

      const mockLedgerData: LedgerResponse = {
        transactions: [
          {
            hash: 'tx-1',
            date: '2024-01-15',
            account_name: 'Checking',
            owner_name: null,
            description: 'Grocery Store',
            amount: -50.25,
            category: null,
            is_recurring: false,
            is_duplicate: false,
          },
        ],
      };

      mockedUseLedger.mockReturnValue(mockQuerySuccess(mockLedgerData));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(
        mockQuerySuccess({ categories: ['Groceries', 'Gas', 'Utilities'] }),
      );
      mockedUseUpdateCategory.mockReturnValue(mockMutation(mockMutateAsync));
      mockedUseUpdateRecurring.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));
      mockedUseUpdateDuplicate.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));

      renderComponent();

      // Click on the category cell to edit
      const categoryButton = screen.getByRole('button', { name: /—/i });
      await user.click(categoryButton);

      // Select a category from the dropdown
      const select = screen.getByRole('combobox');
      await user.selectOptions(select, 'Groceries');

      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledWith({
          hash: 'tx-1',
          category: 'Groceries',
        });
      });
    });
  });

  describe('Recurring checkbox', () => {
    it('calls useUpdateRecurring mutation when recurring checkbox is toggled', async () => {
      const user = userEvent.setup();
      const mockMutateAsync = vi.fn().mockResolvedValue(undefined);

      const mockLedgerData: LedgerResponse = {
        transactions: [
          {
            hash: 'tx-1',
            date: '2024-01-15',
            account_name: 'Checking',
            owner_name: null,
            description: 'Netflix Subscription',
            amount: -15.99,
            category: 'Entertainment',
            is_recurring: false,
            is_duplicate: false,
          },
        ],
      };

      mockedUseLedger.mockReturnValue(mockQuerySuccess(mockLedgerData));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));
      mockedUseUpdateCategory.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));
      mockedUseUpdateRecurring.mockReturnValue(mockMutation(mockMutateAsync));
      mockedUseUpdateDuplicate.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));

      renderComponent();

      const recurringCheckboxes = screen.getAllByRole('checkbox');
      const recurringCheckbox = recurringCheckboxes[0];

      await user.click(recurringCheckbox);

      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledWith({
          hash: 'tx-1',
          recurring: true,
        });
      });
    });
  });

  describe('Duplicate checkbox', () => {
    it('calls useUpdateDuplicate mutation when duplicate checkbox is toggled', async () => {
      const user = userEvent.setup();
      const mockMutateAsync = vi.fn().mockResolvedValue(undefined);

      const mockLedgerData: LedgerResponse = {
        transactions: [
          {
            hash: 'tx-1',
            date: '2024-01-15',
            account_name: 'Checking',
            owner_name: null,
            description: 'Coffee Shop',
            amount: -5.5,
            category: 'Food & Drink',
            is_recurring: false,
            is_duplicate: false,
          },
        ],
      };

      mockedUseLedger.mockReturnValue(mockQuerySuccess(mockLedgerData));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));
      mockedUseUpdateCategory.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));
      mockedUseUpdateRecurring.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));
      mockedUseUpdateDuplicate.mockReturnValue(mockMutation(mockMutateAsync));

      renderComponent();

      const duplicateCheckboxes = screen.getAllByRole('checkbox');
      const duplicateCheckbox = duplicateCheckboxes[1];

      await user.click(duplicateCheckbox);

      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledWith({
          hash: 'tx-1',
          duplicate: true,
        });
      });
    });
  });
});
