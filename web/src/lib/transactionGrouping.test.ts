import { describe, it, expect } from 'vitest';
import { groupByDescription } from './transactionGrouping';
import type { LedgerItem } from './types';

function tx(overrides: Partial<LedgerItem>): LedgerItem {
  return {
    hash: Math.random().toString(36),
    date: '2026-08-01',
    owner_name: null,
    account_name: 'Checking',
    description: 'Unnamed',
    amount: 0,
    category: null,
    tx_type: 'expense',
    is_recurring: false,
    is_duplicate: false,
    ...overrides,
  };
}

describe('groupByDescription', () => {
  it('groups transactions sharing a description, summing amount and counting occurrences', () => {
    const groups = groupByDescription([
      tx({ description: 'Coffee Shop', amount: -5 }),
      tx({ description: 'Coffee Shop', amount: -4 }),
      tx({ description: 'Landlord', amount: -1500 }),
    ]);

    const coffee = groups.find((g) => g.description === 'Coffee Shop');
    expect(coffee).toEqual({ description: 'Coffee Shop', amount: -9, count: 2 });

    const landlord = groups.find((g) => g.description === 'Landlord');
    expect(landlord).toEqual({ description: 'Landlord', amount: -1500, count: 1 });
  });

  it('sorts groups by subtotal magnitude descending, biggest contributor first', () => {
    const groups = groupByDescription([
      tx({ description: 'Small', amount: -10 }),
      tx({ description: 'Biggest', amount: -1500 }),
      tx({ description: 'Medium', amount: -300 }),
    ]);

    expect(groups.map((g) => g.description)).toEqual(['Biggest', 'Medium', 'Small']);
  });

  it('sorts by magnitude regardless of sign, so a large positive group still sorts before a small one', () => {
    const groups = groupByDescription([
      tx({ description: 'Paycheck', amount: 3000 }),
      tx({ description: 'Refund', amount: 20 }),
    ]);

    expect(groups.map((g) => g.description)).toEqual(['Paycheck', 'Refund']);
  });

  it('breaks ties alphabetically for a stable render', () => {
    const groups = groupByDescription([
      tx({ description: 'Zeta', amount: -100 }),
      tx({ description: 'Alpha', amount: -100 }),
    ]);

    expect(groups.map((g) => g.description)).toEqual(['Alpha', 'Zeta']);
  });

  it('returns an empty array for no transactions', () => {
    expect(groupByDescription([])).toEqual([]);
  });
});
