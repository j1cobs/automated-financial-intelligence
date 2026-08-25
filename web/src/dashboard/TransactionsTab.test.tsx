import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  QueryClient,
  QueryClientProvider,
  type UseQueryResult,
  type UseMutationResult,
} from '@tanstack/react-query';
import React from 'react';

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

function mockMutation<TVariables, TContext = unknown>(
  mutateAsync: (vars: TVariables) => Promise<void>,
  overrides: Partial<UseMutationResult<void, Error, TVariables, TContext>> = {},
): UseMutationResult<void, Error, TVariables, TContext> {
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
    ...overrides,
  } as unknown as UseMutationResult<void, Error, TVariables, TContext>;
}

function setDefaultMutations() {
  mockedUseUpdateCategory.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));
  mockedUseUpdateRecurring.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));
  mockedUseUpdateDuplicate.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));
}

describe('TransactionsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Ledger loading and error states', () => {
    it('renders a skeleton for ledger while loading', () => {
      mockedUseLedger.mockReturnValue(mockQueryLoading<LedgerResponse>());
      mockedUseAnomalies.mockReturnValue(mockQueryLoading<AnomaliesResponse>());
      mockedUseCategories.mockReturnValue(mockQueryLoading<CategoriesResponse>());
      setDefaultMutations();

      renderComponent();

      // Both sections render a skeleton while loading (PLAN.md Phase 15, Fix 14);
      // this is at least one of them.
      expect(screen.getAllByRole('status', { name: 'Loading…' }).length).toBeGreaterThan(0);
    });

    it('renders error state for ledger with a retry action wired to refetch', () => {
      const ledgerResult = mockQueryError<LedgerResponse>();
      mockedUseLedger.mockReturnValue(ledgerResult);
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));
      setDefaultMutations();

      renderComponent();

      expect(screen.getByText(/failed to load transactions/i)).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
      expect(ledgerResult.refetch).toHaveBeenCalled();
    });
  });

  describe('Anomalies loading and error states', () => {
    it('renders a skeleton for anomalies while loading', () => {
      mockedUseLedger.mockReturnValue(mockQuerySuccess({ transactions: [] }));
      mockedUseAnomalies.mockReturnValue(mockQueryLoading<AnomaliesResponse>());
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));
      setDefaultMutations();

      renderComponent();

      expect(screen.getByRole('status', { name: 'Loading…' })).toBeInTheDocument();
    });

    it('renders error state for anomalies with a retry action wired to refetch', () => {
      const anomaliesResult = mockQueryError<AnomaliesResponse>();
      mockedUseLedger.mockReturnValue(mockQuerySuccess({ transactions: [] }));
      mockedUseAnomalies.mockReturnValue(anomaliesResult);
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));
      setDefaultMutations();

      renderComponent();

      expect(screen.getByText(/failed to load anomalies/i)).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
      expect(anomaliesResult.refetch).toHaveBeenCalled();
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
      setDefaultMutations();

      renderComponent();

      expect(screen.getByText('Grocery Store')).toBeInTheDocument();
      expect(screen.getByText('Gas Station')).toBeInTheDocument();
      expect(screen.getByText('Groceries')).toBeInTheDocument();
      expect(screen.getByText('John Doe')).toBeInTheDocument();
      expect(screen.getByText('2 transactions')).toBeInTheDocument();
    });

    it('stays on the plain (unvirtualized) table at 50 transactions', () => {
      const mockLedgerData: LedgerResponse = {
        transactions: Array.from({ length: 50 }, (_, i) => ({
          hash: `tx-${i}`,
          date: '2024-01-15',
          account_name: 'Checking',
          owner_name: null,
          description: `Transaction ${i}`,
          amount: -10,
          category: null,
          is_recurring: false,
          is_duplicate: false,
        })),
      };
      mockedUseLedger.mockReturnValue(mockQuerySuccess(mockLedgerData));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));
      setDefaultMutations();

      const { container } = renderComponent();

      // Every row mounted -- the plain path, not the fixed-height scroll container.
      expect(screen.getAllByText(/^Transaction \d+$/)).toHaveLength(50);
      expect(container.querySelector('.max-h-\\[70vh\\]')).not.toBeInTheDocument();
    });

    it('switches to the virtualized table above the threshold and does not mount every row', () => {
      // jsdom never lays elements out, so `offsetHeight`/`offsetWidth` --
      // what @tanstack/react-virtual actually measures the scroll container
      // with -- are always 0, which would compute an empty visible window.
      // Stub a viewport-sized box so it windows for real.
      const originalOffsetHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight');
      const originalOffsetWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth');
      Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, value: 500 });
      Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, value: 800 });

      try {
        const mockLedgerData: LedgerResponse = {
          transactions: Array.from({ length: 200 }, (_, i) => ({
            hash: `tx-${i}`,
            date: '2024-01-15',
            account_name: 'Checking',
            owner_name: null,
            description: `Transaction ${i}`,
            amount: -10,
            category: null,
            is_recurring: false,
            is_duplicate: false,
          })),
        };
        mockedUseLedger.mockReturnValue(mockQuerySuccess(mockLedgerData));
        mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
        mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));
        setDefaultMutations();

        const { container } = renderComponent();

        expect(screen.getByText('200 transactions')).toBeInTheDocument();
        expect(container.querySelector('.max-h-\\[70vh\\]')).toBeInTheDocument();
        // The whole point: far fewer than 200 rows actually mounted in the DOM.
        const renderedRows = screen.getAllByText(/^Transaction \d+$/);
        expect(renderedRows.length).toBeGreaterThan(0);
        expect(renderedRows.length).toBeLessThan(200);
      } finally {
        if (originalOffsetHeight) {
          Object.defineProperty(HTMLElement.prototype, 'offsetHeight', originalOffsetHeight);
        }
        if (originalOffsetWidth) {
          Object.defineProperty(HTMLElement.prototype, 'offsetWidth', originalOffsetWidth);
        }
      }
    });

    it('renders empty ledger message when no transactions', () => {
      mockedUseLedger.mockReturnValue(mockQuerySuccess({ transactions: [] }));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));

      renderComponent();

      expect(screen.getByText(/no transactions found/i)).toBeInTheDocument();
    });

    it('shows the three explanatory captions', () => {
      mockedUseLedger.mockReturnValue(mockQuerySuccess({ transactions: [] }));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));

      renderComponent();

      expect(
        screen.getByText(
          /Tick Duplicate to exclude a double-posted transaction from every total and chart\. Flagged rows stay listed here so you can untick them\./i,
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Edit categories inline — changes persist across pipeline re-runs\./i),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          /Positive amounts are income or credits\. Negative amounts are expenses or debits\./i,
        ),
      ).toBeInTheDocument();
    });

    it('sorts by amount when the Amount header is clicked', async () => {
      const user = userEvent.setup();
      const mockLedgerData: LedgerResponse = {
        transactions: [
          {
            hash: 'tx-small',
            date: '2024-01-15',
            account_name: 'Checking',
            owner_name: null,
            description: 'Small charge',
            amount: -10,
            category: null,
            is_recurring: false,
            is_duplicate: false,
          },
          {
            hash: 'tx-big',
            date: '2024-01-14',
            account_name: 'Checking',
            owner_name: null,
            description: 'Big charge',
            amount: -500,
            category: null,
            is_recurring: false,
            is_duplicate: false,
          },
        ],
      };

      mockedUseLedger.mockReturnValue(mockQuerySuccess(mockLedgerData));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));
      setDefaultMutations();

      renderComponent();

      // Default sort is by date descending: "Small charge" (Jan 15) before "Big charge" (Jan 14).
      let rows = screen.getAllByRole('row').slice(1); // drop header row
      expect(rows[0]).toHaveTextContent('Small charge');
      expect(rows[1]).toHaveTextContent('Big charge');

      await user.click(screen.getByRole('button', { name: /sort by amount/i }));

      // First click on a new sort column sorts descending: -10 (Small charge)
      // before -500 (Big charge).
      rows = screen.getAllByRole('row').slice(1);
      expect(rows[0]).toHaveTextContent('Small charge');
      expect(rows[1]).toHaveTextContent('Big charge');

      await user.click(screen.getByRole('button', { name: /sort by amount/i }));

      // Second click flips to ascending: -500 (Big charge) before -10 (Small charge).
      rows = screen.getAllByRole('row').slice(1);
      expect(rows[0]).toHaveTextContent('Big charge');
      expect(rows[1]).toHaveTextContent('Small charge');
    });

    it('visually distinguishes duplicate-flagged rows', () => {
      const mockLedgerData: LedgerResponse = {
        transactions: [
          {
            hash: 'tx-dup',
            date: '2024-01-15',
            account_name: 'Checking',
            owner_name: null,
            description: 'Duplicate Charge',
            amount: -25,
            category: null,
            is_recurring: false,
            is_duplicate: true,
          },
        ],
      };

      mockedUseLedger.mockReturnValue(mockQuerySuccess(mockLedgerData));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));
      setDefaultMutations();

      renderComponent();

      const row = screen.getByText('Duplicate Charge').closest('tr');
      expect(row).not.toBeNull();
      expect(row?.className).toMatch(/bg-surface-2/);
      expect(screen.getByText('Excluded')).toBeInTheDocument();
    });
  });

  describe('Anomalies rendering', () => {
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
        {
          date: '2024-01-18',
          account_name: 'Checking',
          owner_name: 'Jane Doe',
          description: 'Odd Refund',
          amount: 300.0,
          category: 'Refund',
          outlier_score: 0.4,
        },
      ],
    };

    it('renders the anomaly scatter plot with a point per anomaly', () => {
      mockedUseLedger.mockReturnValue(mockQuerySuccess({ transactions: [] }));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess(mockAnomaliesData));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));

      const { container } = renderComponent();

      const points = container.querySelectorAll('.recharts-scatter-symbol');
      expect(points.length).toBe(mockAnomaliesData.anomalies.length);
      expect(screen.getByText(/higher score = more unusual transaction/i)).toBeInTheDocument();
    });

    it('renders empty anomalies message when none detected', () => {
      mockedUseLedger.mockReturnValue(mockQuerySuccess({ transactions: [] }));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));

      renderComponent();

      expect(screen.getByText(/no anomalies detected/i)).toBeInTheDocument();
    });
  });

  describe('Failed ledger edits', () => {
    it('shows an inline error banner when a category edit fails', () => {
      mockedUseLedger.mockReturnValue(mockQuerySuccess({ transactions: [] }));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));
      mockedUseUpdateCategory.mockReturnValue(
        mockMutation(vi.fn().mockRejectedValue(new Error('fail')), { isError: true }),
      );
      mockedUseUpdateRecurring.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));
      mockedUseUpdateDuplicate.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));

      renderComponent();

      expect(
        screen.getByText('Failed to save your change. It has been reverted — please try again.'),
      ).toBeInTheDocument();
    });

    it('shows no error banner when every mutation is in its default (non-error) state', () => {
      mockedUseLedger.mockReturnValue(mockQuerySuccess({ transactions: [] }));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));
      setDefaultMutations();

      renderComponent();

      expect(
        screen.queryByText('Failed to save your change. It has been reverted — please try again.'),
      ).not.toBeInTheDocument();
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
