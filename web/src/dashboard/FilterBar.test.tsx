import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act } from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FilterBar } from './FilterBar';
import { FilterProvider } from '../lib/FilterContext';
import type { FilterOptions } from '../lib/types';
import type { UseQueryResult } from '@tanstack/react-query';

vi.mock('../lib/queries', () => ({
  useFilterOptions: vi.fn(),
}));

import { useFilterOptions } from '../lib/queries';

const mockedUseFilterOptions = vi.mocked(useFilterOptions);

const mockOptions: FilterOptions = {
  owners: ['Alice', 'Bob'],
  categories: ['Groceries', 'Utilities'],
  accounts: ['Chase Checking', 'Ally Savings'],
  months: [
    { key: '2026-01', label: 'January 2026' },
    { key: '2026-02', label: 'February 2026' },
  ],
  amount_min: 0,
  amount_max: 5000,
};

function renderFilterBar() {
  return render(
    <FilterProvider>
      <FilterBar />
    </FilterProvider>,
  );
}

describe('FilterBar', () => {
  beforeEach(() => {
    // Clean slate for the URL FilterProvider reads/writes on each test.
    window.history.replaceState(null, '', '/');
    mockedUseFilterOptions.mockReturnValue({
      data: mockOptions,
      isLoading: false,
      error: null,
    } as unknown as UseQueryResult<FilterOptions, Error>);
  });

  it('changing the period updates filter state and shows a chip for it', async () => {
    const user = userEvent.setup();
    renderFilterBar();

    const periodSelect = screen.getByLabelText('Period') as HTMLSelectElement;
    expect(periodSelect.value).toBe('last_3_months');

    await user.selectOptions(periodSelect, 'last_30_days');

    expect(periodSelect.value).toBe('last_30_days');
    expect(screen.getByText('Period: Last 30 days')).toBeInTheDocument();
  });

  it('selecting an owner then clicking its chip removes just that owner', async () => {
    const user = userEvent.setup();
    renderFilterBar();

    await user.click(screen.getByLabelText('Owner'));
    const ownerDialog = screen.getByRole('dialog', { name: 'Owner' });
    await user.click(within(ownerDialog).getByRole('checkbox', { name: 'Alice' }));
    await user.click(within(ownerDialog).getByRole('checkbox', { name: 'Bob' }));

    expect(screen.getByRole('button', { name: /remove filter: alice/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /remove filter: bob/i })).toBeInTheDocument();

    const removeAlice = screen.getByRole('button', { name: /remove filter: alice/i });
    await user.click(removeAlice);

    expect(screen.queryByRole('button', { name: /remove filter: alice/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /remove filter: bob/i })).toBeInTheDocument();
  });

  it('"Clear all" resets every filter and hides the chip row', async () => {
    const user = userEvent.setup();
    renderFilterBar();

    const periodSelect = screen.getByLabelText('Period') as HTMLSelectElement;
    await user.selectOptions(periodSelect, 'last_30_days');
    await user.click(screen.getByLabelText('Owner'));
    await user.click(
      within(screen.getByRole('dialog', { name: 'Owner' })).getByRole('checkbox', { name: 'Alice' }),
    );

    expect(screen.getByText('Period: Last 30 days')).toBeInTheDocument();

    const clearAllButtons = screen.getAllByRole('button', { name: /clear all/i });
    await user.click(clearAllButtons[0]);

    expect(periodSelect.value).toBe('last_3_months');
    expect(screen.queryByText('Period: Last 30 days')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /remove filter: alice/i })).not.toBeInTheDocument();
  });

  it('debounces the description search by 300ms before it becomes an active filter', async () => {
    vi.useFakeTimers();
    try {
      renderFilterBar();

      const moreButton = screen.getByRole('button', { name: 'More filters' });
      fireEvent.click(moreButton);

      const dialog = screen.getByRole('dialog', { name: 'More filters' });
      const searchInput = within(dialog).getByLabelText('Description search');

      fireEvent.change(searchInput, { target: { value: 'coffee' } });

      // Not yet committed to filter state.
      expect(screen.queryByText('Search: "coffee"')).not.toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(299);
      });
      expect(screen.queryByText('Search: "coffee"')).not.toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(screen.getByText('Search: "coffee"')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('More filters popover closes on Escape and returns focus to its trigger', async () => {
    const user = userEvent.setup();
    renderFilterBar();

    const moreButton = screen.getByRole('button', { name: 'More filters' });
    expect(moreButton).toHaveAttribute('aria-expanded', 'false');

    await user.click(moreButton);
    expect(moreButton).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('dialog', { name: 'More filters' })).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByRole('dialog', { name: 'More filters' })).not.toBeInTheDocument();
    expect(moreButton).toHaveAttribute('aria-expanded', 'false');
    expect(moreButton).toHaveFocus();
  });
});

afterEach(() => {
  vi.useRealTimers();
});
