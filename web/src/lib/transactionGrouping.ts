import type { LedgerItem } from './types';

export interface DescriptionGroup {
  description: string;
  /** Sum of every transaction's `amount` sharing this description --
   *  positive within the Income column, negative within Expenses. */
  amount: number;
  count: number;
}

/**
 * Groups transactions by `description`, summing `amount` and counting
 * occurrences per group, sorted by subtotal magnitude descending (biggest
 * contributor first, regardless of the column's sign) -- ties broken
 * alphabetically for a stable render.
 */
export function groupByDescription(transactions: LedgerItem[]): DescriptionGroup[] {
  const groups = new Map<string, DescriptionGroup>();
  for (const tx of transactions) {
    const existing = groups.get(tx.description);
    if (existing) {
      existing.amount += tx.amount;
      existing.count += 1;
    } else {
      groups.set(tx.description, { description: tx.description, amount: tx.amount, count: 1 });
    }
  }
  return Array.from(groups.values()).sort((a, b) => {
    const byMagnitude = Math.abs(b.amount) - Math.abs(a.amount);
    return byMagnitude !== 0 ? byMagnitude : a.description.localeCompare(b.description);
  });
}
