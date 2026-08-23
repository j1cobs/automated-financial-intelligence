import { useState } from 'react';
import { useLedger, useAnomalies, useCategories } from '../lib/queries';
import { useUpdateCategory, useUpdateRecurring, useUpdateDuplicate } from '../lib/mutations';
import type { LedgerItem, AnomalyItem } from '../lib/types';

export function TransactionsTab() {
  const ledgerQuery = useLedger();
  const anomaliesQuery = useAnomalies();
  const categoriesQuery = useCategories();

  const updateCategory = useUpdateCategory();
  const updateRecurring = useUpdateRecurring();
  const updateDuplicate = useUpdateDuplicate();

  const [editingHash, setEditingHash] = useState<string | null>(null);
  const [editingCategory, setEditingCategory] = useState<string>('');

  const handleCategoryChange = async (hash: string, newCategory: string) => {
    setEditingHash(null);
    await updateCategory.mutateAsync({ hash, category: newCategory });
  };

  const handleRecurringToggle = async (hash: string, currentValue: boolean) => {
    await updateRecurring.mutateAsync({ hash, recurring: !currentValue });
  };

  const handleDuplicateToggle = async (hash: string, currentValue: boolean) => {
    await updateDuplicate.mutateAsync({ hash, duplicate: !currentValue });
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(amount);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  return (
    <div className="space-y-6 sm:space-y-8">
      {/* Ledger Section */}
      <div>
        <h2 className="text-base sm:text-lg font-semibold text-slate-800 mb-3 sm:mb-4">Ledger</h2>

        {ledgerQuery.isLoading && (
          <div className="py-8 text-center text-sm text-slate-500">Loading transactions...</div>
        )}

        {ledgerQuery.isError && (
          <div className="py-8 px-4 bg-red-50 border border-red-200 rounded text-sm text-red-700">
            Failed to load transactions. Please try again.
          </div>
        )}

        {ledgerQuery.data && (
          <div className="overflow-x-auto border border-slate-200 rounded-lg">
            <table className="min-w-full text-xs sm:text-sm">
              <thead>
                <tr className="border-b bg-slate-50">
                  <th className="px-2 sm:px-4 py-2 sm:py-3 text-left font-semibold text-slate-700">Date</th>
                  <th className="px-2 sm:px-4 py-2 sm:py-3 text-left font-semibold text-slate-700">
                    Account
                  </th>
                  <th className="px-2 sm:px-4 py-2 sm:py-3 text-left font-semibold text-slate-700">
                    Description
                  </th>
                  <th className="px-2 sm:px-4 py-2 sm:py-3 text-right font-semibold text-slate-700">
                    Amount
                  </th>
                  <th className="px-2 sm:px-4 py-2 sm:py-3 text-left font-semibold text-slate-700">
                    Category
                  </th>
                  <th className="px-2 sm:px-4 py-2 sm:py-3 text-center font-semibold text-slate-700">
                    Recurring
                  </th>
                  <th className="px-2 sm:px-4 py-2 sm:py-3 text-center font-semibold text-slate-700">
                    Duplicate
                  </th>
                </tr>
              </thead>
              <tbody>
                {ledgerQuery.data.transactions.length === 0 ? (
                  <tr>
                    <td
                      colSpan={7}
                      className="px-2 sm:px-4 py-6 sm:py-8 text-center text-xs sm:text-sm text-slate-500"
                    >
                      No transactions found
                    </td>
                  </tr>
                ) : (
                  ledgerQuery.data.transactions.map((tx: LedgerItem) => (
                    <tr key={tx.hash} className="border-b hover:bg-slate-50">
                      <td className="px-2 sm:px-4 py-2 sm:py-3 text-slate-700">{formatDate(tx.date)}</td>
                      <td className="px-2 sm:px-4 py-2 sm:py-3 text-slate-700 whitespace-nowrap">
                        {tx.account_name}
                        {tx.owner_name && <div className="text-xs text-slate-500">{tx.owner_name}</div>}
                      </td>
                      <td className="px-2 sm:px-4 py-2 sm:py-3 text-slate-700">{tx.description}</td>
                      <td className="px-2 sm:px-4 py-2 sm:py-3 text-right text-slate-700 font-mono">
                        {formatCurrency(tx.amount)}
                      </td>
                      <td className="px-2 sm:px-4 py-2 sm:py-3">
                        {editingHash === tx.hash ? (
                          <select
                            autoFocus
                            value={editingCategory}
                            onChange={(e) => handleCategoryChange(tx.hash, e.target.value)}
                            onBlur={() => setEditingHash(null)}
                            className="border border-slate-300 rounded px-2 py-1 text-xs sm:text-sm w-full min-h-9"
                          >
                            <option value="">Uncategorized</option>
                            {categoriesQuery.data?.categories.map((cat) => (
                              <option key={cat} value={cat}>
                                {cat}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <button
                            onClick={() => {
                              setEditingHash(tx.hash);
                              setEditingCategory(tx.category || '');
                            }}
                            className="text-slate-700 hover:bg-slate-200 rounded px-2 py-1 text-left block w-full min-h-9 flex items-center"
                          >
                            {tx.category || <span className="text-slate-400">—</span>}
                          </button>
                        )}
                      </td>
                      <td className="px-2 sm:px-4 py-2 sm:py-3 text-center">
                        <input
                          type="checkbox"
                          checked={tx.is_recurring}
                          onChange={() => handleRecurringToggle(tx.hash, tx.is_recurring)}
                          disabled={updateRecurring.isPending}
                          className="w-5 h-5 cursor-pointer"
                          aria-label={`Mark ${tx.description} as ${tx.is_recurring ? 'non-recurring' : 'recurring'}`}
                        />
                      </td>
                      <td className="px-2 sm:px-4 py-2 sm:py-3 text-center">
                        <input
                          type="checkbox"
                          checked={tx.is_duplicate}
                          onChange={() => handleDuplicateToggle(tx.hash, tx.is_duplicate)}
                          disabled={updateDuplicate.isPending}
                          className="w-5 h-5 cursor-pointer"
                          aria-label={`Mark ${tx.description} as ${tx.is_duplicate ? 'not a duplicate' : 'duplicate'}`}
                        />
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Anomalies Section */}
      <div>
        <h2 className="text-base sm:text-lg font-semibold text-slate-800 mb-3 sm:mb-4">Anomalies</h2>

        {anomaliesQuery.isLoading && (
          <div className="py-8 text-center text-sm text-slate-500">Loading anomalies...</div>
        )}

        {anomaliesQuery.isError && (
          <div className="py-8 px-4 bg-red-50 border border-red-200 rounded text-sm text-red-700">
            Failed to load anomalies. Please try again.
          </div>
        )}

        {anomaliesQuery.data && (
          <div className="overflow-x-auto border border-slate-200 rounded-lg">
            <table className="min-w-full text-xs sm:text-sm">
              <thead>
                <tr className="border-b bg-slate-50">
                  <th className="px-2 sm:px-4 py-2 sm:py-3 text-left font-semibold text-slate-700">Date</th>
                  <th className="px-2 sm:px-4 py-2 sm:py-3 text-left font-semibold text-slate-700">
                    Account
                  </th>
                  <th className="px-2 sm:px-4 py-2 sm:py-3 text-left font-semibold text-slate-700">
                    Description
                  </th>
                  <th className="px-2 sm:px-4 py-2 sm:py-3 text-right font-semibold text-slate-700">
                    Amount
                  </th>
                  <th className="px-2 sm:px-4 py-2 sm:py-3 text-left font-semibold text-slate-700">
                    Category
                  </th>
                  <th className="px-2 sm:px-4 py-2 sm:py-3 text-right font-semibold text-slate-700">
                    Outlier Score
                  </th>
                </tr>
              </thead>
              <tbody>
                {anomaliesQuery.data.anomalies.length === 0 ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-2 sm:px-4 py-6 sm:py-8 text-center text-xs sm:text-sm text-slate-500"
                    >
                      No anomalies detected
                    </td>
                  </tr>
                ) : (
                  anomaliesQuery.data.anomalies.map((anomaly: AnomalyItem, idx: number) => (
                    <tr key={`${anomaly.date}-${idx}`} className="border-b hover:bg-slate-50">
                      <td className="px-2 sm:px-4 py-2 sm:py-3 text-slate-700">{formatDate(anomaly.date)}</td>
                      <td className="px-2 sm:px-4 py-2 sm:py-3 text-slate-700 whitespace-nowrap">
                        {anomaly.account_name}
                        {anomaly.owner_name && (
                          <div className="text-xs text-slate-500">{anomaly.owner_name}</div>
                        )}
                      </td>
                      <td className="px-2 sm:px-4 py-2 sm:py-3 text-slate-700">{anomaly.description}</td>
                      <td className="px-2 sm:px-4 py-2 sm:py-3 text-right text-slate-700 font-mono">
                        {formatCurrency(anomaly.amount)}
                      </td>
                      <td className="px-2 sm:px-4 py-2 sm:py-3 text-slate-700">
                        {anomaly.category || <span className="text-slate-400">—</span>}
                      </td>
                      <td className="px-2 sm:px-4 py-2 sm:py-3 text-right font-mono text-orange-600">
                        {anomaly.outlier_score.toFixed(3)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
