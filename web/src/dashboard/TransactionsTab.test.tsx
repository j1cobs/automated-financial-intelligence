import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
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
import type {
  LedgerResponse,
  AnomaliesResponse,
  CategoriesResponse,
  CategoryUpdateResponse,
} from '../lib/types';

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

function mockMutation<TData, TVariables, TContext = unknown>(
  mutateAsync: (vars: TVariables) => Promise<TData>,
  overrides: Partial<UseMutationResult<TData, Error, TVariables, TContext>> = {},
): UseMutationResult<TData, Error, TVariables, TContext> {
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
  } as unknown as UseMutationResult<TData, Error, TVariables, TContext>;
}

function setDefaultMutations() {
  mockedUseUpdateCategory.mockReturnValue(
    mockMutation(vi.fn().mockResolvedValue({ backfilled_count: 0 } satisfies CategoryUpdateResponse)),
  );
  mockedUseUpdateRecurring.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));
  mockedUseUpdateDuplicate.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));
}

describe('TransactionsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Clear localStorage between tests to avoid state leakage
    localStorage.clear();
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
            tx_type: 'expense',
            is_recurring: false,
            is_duplicate: false,
            pfc_detailed: null,
            category_source: null,
          },
          {
            hash: 'tx-2',
            date: '2024-01-14',
            account_name: 'Credit Card',
            owner_name: null,
            description: 'Gas Station',
            amount: -40.0,
            category: null,
            tx_type: 'expense',
            is_recurring: true,
            is_duplicate: false,
            pfc_detailed: null,
            category_source: null,
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
          tx_type: 'expense',
          is_recurring: false,
          is_duplicate: false,
          pfc_detailed: null,
          category_source: null,
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
            tx_type: 'expense',
            is_recurring: false,
            is_duplicate: false,
            pfc_detailed: null,
            category_source: null,
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
            tx_type: 'expense',
            is_recurring: false,
            is_duplicate: false,
            pfc_detailed: null,
            category_source: null,
          },
          {
            hash: 'tx-big',
            date: '2024-01-14',
            account_name: 'Checking',
            owner_name: null,
            description: 'Big charge',
            amount: -500,
            category: null,
            tx_type: 'expense',
            is_recurring: false,
            is_duplicate: false,
            pfc_detailed: null,
            category_source: null,
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
            tx_type: 'expense',
            is_recurring: false,
            is_duplicate: true,
            pfc_detailed: null,
            category_source: null,
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
      const mockMutateAsync = vi
        .fn()
        .mockResolvedValue({ backfilled_count: 0 } satisfies CategoryUpdateResponse);

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
            tx_type: 'expense',
            is_recurring: false,
            is_duplicate: false,
            pfc_detailed: null,
            category_source: null,
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

    it('renders exactly one "Uncategorized" option and submits the real category value, not an empty string', async () => {
      const user = userEvent.setup();
      const mockMutateAsync = vi
        .fn()
        .mockResolvedValue({ backfilled_count: 0 } satisfies CategoryUpdateResponse);

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
            tx_type: 'expense',
            is_recurring: false,
            is_duplicate: false,
            pfc_detailed: null,
            category_source: null,
          },
        ],
      };

      mockedUseLedger.mockReturnValue(mockQuerySuccess(mockLedgerData));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(
        mockQuerySuccess({ categories: ['FOOD_AND_DRINK', 'UNCATEGORIZED'] }),
      );
      mockedUseUpdateCategory.mockReturnValue(mockMutation(mockMutateAsync));
      mockedUseUpdateRecurring.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));
      mockedUseUpdateDuplicate.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));

      renderComponent();

      const categoryButton = screen.getByRole('button', { name: /—/i });
      await user.click(categoryButton);

      const select = screen.getByRole('combobox');
      const uncategorizedOptions = within(select).getAllByText('Uncategorized');
      expect(uncategorizedOptions).toHaveLength(1);

      await user.selectOptions(select, 'Uncategorized');

      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledWith({
          hash: 'tx-1',
          category: 'UNCATEGORIZED',
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
            tx_type: 'expense',
            is_recurring: false,
            is_duplicate: false,
            pfc_detailed: null,
            category_source: null,
          },
        ],
      };

      mockedUseLedger.mockReturnValue(mockQuerySuccess(mockLedgerData));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));
      mockedUseUpdateCategory.mockReturnValue(
        mockMutation(vi.fn().mockResolvedValue({ backfilled_count: 0 } satisfies CategoryUpdateResponse)),
      );
      mockedUseUpdateRecurring.mockReturnValue(mockMutation(mockMutateAsync));
      mockedUseUpdateDuplicate.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));

      renderComponent();

      // Find the recurring checkbox for the specific transaction (not the "Show category detail" checkbox)
      const recurringCheckbox = screen.getByRole('checkbox', {
        name: /Mark Netflix Subscription as recurring/i,
      });

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
            tx_type: 'expense',
            is_recurring: false,
            is_duplicate: false,
            pfc_detailed: null,
            category_source: null,
          },
        ],
      };

      mockedUseLedger.mockReturnValue(mockQuerySuccess(mockLedgerData));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: [] }));
      mockedUseUpdateCategory.mockReturnValue(
        mockMutation(vi.fn().mockResolvedValue({ backfilled_count: 0 } satisfies CategoryUpdateResponse)),
      );
      mockedUseUpdateRecurring.mockReturnValue(mockMutation(vi.fn().mockResolvedValue(undefined)));
      mockedUseUpdateDuplicate.mockReturnValue(mockMutation(mockMutateAsync));

      renderComponent();

      // Find the duplicate checkbox for the specific transaction (not the "Show category detail" checkbox)
      const duplicateCheckbox = screen.getByRole('checkbox', {
        name: /Mark Coffee Shop as duplicate/i,
      });

      await user.click(duplicateCheckbox);

      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledWith({
          hash: 'tx-1',
          duplicate: true,
        });
      });
    });
  });

  describe('Plaid detail column (pfc_detailed) toggle', () => {
    it('does not render the "Plaid detail" column by default when localStorage is empty', () => {
      const mockLedgerData: LedgerResponse = {
        transactions: [
          {
            hash: 'tx-1',
            date: '2024-01-15',
            account_name: 'Checking',
            owner_name: null,
            description: 'Grocery Store',
            amount: -50.25,
            category: 'Groceries',
            tx_type: 'expense',
            is_recurring: false,
            is_duplicate: false,
            pfc_detailed: 'FOOD_AND_DRINK_GROCERIES',
            category_source: 'plaid',
          },
        ],
      };

      mockedUseLedger.mockReturnValue(mockQuerySuccess(mockLedgerData));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: ['Groceries'] }));
      setDefaultMutations();

      renderComponent();

      // The "Show category detail" checkbox should exist and be unchecked
      const checkbox = screen.getByRole('checkbox', { name: /show category detail/i });
      expect(checkbox).toBeInTheDocument();
      expect(checkbox).not.toBeChecked();

      // The "Plaid detail" column header should not be in the document
      expect(screen.queryByText('Plaid detail')).not.toBeInTheDocument();
    });

    it('renders the "Plaid detail" column with pfc_detailed values when checkbox is clicked', async () => {
      const user = userEvent.setup();
      const mockLedgerData: LedgerResponse = {
        transactions: [
          {
            hash: 'tx-1',
            date: '2024-01-15',
            account_name: 'Checking',
            owner_name: null,
            description: 'Grocery Store',
            amount: -50.25,
            category: 'Groceries',
            tx_type: 'expense',
            is_recurring: false,
            is_duplicate: false,
            pfc_detailed: 'FOOD_AND_DRINK_GROCERIES',
            category_source: 'plaid',
          },
          {
            hash: 'tx-2',
            date: '2024-01-14',
            account_name: 'Credit Card',
            owner_name: null,
            description: 'Gas Station',
            amount: -40.0,
            category: 'Gas',
            tx_type: 'expense',
            is_recurring: true,
            is_duplicate: false,
            pfc_detailed: null,
            category_source: null,
          },
        ],
      };

      mockedUseLedger.mockReturnValue(mockQuerySuccess(mockLedgerData));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: ['Groceries', 'Gas'] }));
      setDefaultMutations();

      renderComponent();

      // Column should not exist initially
      expect(screen.queryByText('Plaid detail')).not.toBeInTheDocument();

      // Click the "Show category detail" checkbox
      const checkbox = screen.getByRole('checkbox', { name: /show category detail/i });
      await user.click(checkbox);

      // Column header should now appear
      expect(screen.getByText('Plaid detail')).toBeInTheDocument();

      // pfc_detailed values should be rendered in the column
      expect(screen.getByText('FOOD_AND_DRINK_GROCERIES')).toBeInTheDocument();

      // Null pfc_detailed should render as "—"
      const gasRow = screen.getByText('Gas Station').closest('tr');
      expect(within(gasRow!).getByText('—')).toBeInTheDocument();
    });

    it('persists the toggle state to localStorage and restores it on fresh mount', async () => {
      const user = userEvent.setup();
      const mockLedgerData: LedgerResponse = {
        transactions: [
          {
            hash: 'tx-1',
            date: '2024-01-15',
            account_name: 'Checking',
            owner_name: null,
            description: 'Test Transaction',
            amount: -25.0,
            category: 'Testing',
            tx_type: 'expense',
            is_recurring: false,
            is_duplicate: false,
            pfc_detailed: 'TEST_DETAILED',
            category_source: 'plaid',
          },
        ],
      };

      mockedUseLedger.mockReturnValue(mockQuerySuccess(mockLedgerData));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: ['Testing'] }));
      setDefaultMutations();

      // First render: column not visible
      const { unmount } = renderComponent();
      expect(screen.queryByText('Plaid detail')).not.toBeInTheDocument();

      // Toggle the checkbox on
      const checkbox = screen.getByRole('checkbox', { name: /show category detail/i });
      await user.click(checkbox);
      expect(screen.getByText('Plaid detail')).toBeInTheDocument();

      // Unmount to simulate page unload
      unmount();

      // Fresh mount (simulating page reload) with same mocked data
      renderComponent();

      // The column should be visible immediately without toggling again
      expect(screen.getByText('Plaid detail')).toBeInTheDocument();
      expect(screen.getByText('TEST_DETAILED')).toBeInTheDocument();

      // The checkbox should be checked
      const newCheckbox = screen.getByRole('checkbox', { name: /show category detail/i });
      expect(newCheckbox).toBeChecked();
    });

    it('renders bg-surface-2 class on detail cells only when category_source is "merchant"', async () => {
      const user = userEvent.setup();
      const mockLedgerData: LedgerResponse = {
        transactions: [
          {
            hash: 'tx-merchant',
            date: '2024-01-15',
            account_name: 'Checking',
            owner_name: null,
            description: 'Merchant Transaction',
            amount: -30.0,
            category: 'Groceries',
            tx_type: 'expense',
            is_recurring: false,
            is_duplicate: false,
            pfc_detailed: 'CUSTOM_MERCHANT_CATEGORY',
            category_source: 'merchant',
          },
          {
            hash: 'tx-plaid',
            date: '2024-01-14',
            account_name: 'Checking',
            owner_name: null,
            description: 'Plaid Transaction',
            amount: -20.0,
            category: 'Gas',
            tx_type: 'expense',
            is_recurring: false,
            is_duplicate: false,
            pfc_detailed: 'TRANSPORTATION_FUEL',
            category_source: 'plaid',
          },
          {
            hash: 'tx-null-source',
            date: '2024-01-13',
            account_name: 'Checking',
            owner_name: null,
            description: 'Old Transaction',
            amount: -10.0,
            category: 'Other',
            tx_type: 'expense',
            is_recurring: false,
            is_duplicate: false,
            pfc_detailed: 'SOME_CATEGORY',
            category_source: null,
          },
        ],
      };

      mockedUseLedger.mockReturnValue(mockQuerySuccess(mockLedgerData));
      mockedUseAnomalies.mockReturnValue(mockQuerySuccess({ anomalies: [] }));
      mockedUseCategories.mockReturnValue(mockQuerySuccess({ categories: ['Groceries', 'Gas', 'Other'] }));
      setDefaultMutations();

      renderComponent();

      // Toggle on the detail column
      const checkbox = screen.getByRole('checkbox', { name: /show category detail/i });
      await user.click(checkbox);

      // Find the rows by their descriptions
      const merchantRow = screen.getByText('Merchant Transaction').closest('tr');
      const plaidRow = screen.getByText('Plaid Transaction').closest('tr');
      const nullSourceRow = screen.getByText('Old Transaction').closest('tr');

      // The merchant row's detail cell should have bg-surface-2
      const merchantDetailCell = within(merchantRow!).getByText('CUSTOM_MERCHANT_CATEGORY').closest('td');
      expect(merchantDetailCell?.className).toMatch(/bg-surface-2/);

      // The plaid row's detail cell should NOT have bg-surface-2
      const plaidDetailCell = within(plaidRow!).getByText('TRANSPORTATION_FUEL').closest('td');
      expect(plaidDetailCell?.className).not.toMatch(/bg-surface-2/);

      // The null-source row's detail cell should NOT have bg-surface-2
      const nullSourceDetailCell = within(nullSourceRow!).getByText('SOME_CATEGORY').closest('td');
      expect(nullSourceDetailCell?.className).not.toMatch(/bg-surface-2/);
    });
  });
});
