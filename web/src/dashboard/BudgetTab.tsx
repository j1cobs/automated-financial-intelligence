/**
 * Budget tab — per-category spend vs. limit, projected end-of-month.
 * Uses `useBudget()` from `lib/queries.ts` (returns `BudgetResponse` from
 * `lib/types.ts`) and `useUpsertBudget()` from `lib/mutations.ts` for editing limits.
 */

import { useState } from 'react';
import { useBudget } from '../lib/queries';
import { useUpsertBudget } from '../lib/mutations';
import type { BudgetItem } from '../lib/types';

export function BudgetTab() {
  const { data, isPending, error } = useBudget();
  const upsertMutation = useUpsertBudget();
  const [editingCategory, setEditingCategory] = useState<string | null>(null);
  const [editValues, setEditValues] = useState<Record<string, number>>({});

  if (isPending) {
    return (
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-slate-800">Budget</h2>
        <div className="text-slate-500">Loading budget data...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-slate-800">Budget</h2>
        <div className="rounded-md bg-red-50 p-4 text-red-700">
          Failed to load budget data. Please try again.
        </div>
      </div>
    );
  }

  const budgetItems = data?.items || [];

  const handleEdit = (category: string, currentLimit: number | null) => {
    setEditingCategory(category);
    setEditValues({ [category]: currentLimit || 0 });
  };

  const handleSave = async (category: string) => {
    const newLimit = editValues[category];
    if (newLimit !== undefined) {
      try {
        await upsertMutation.mutateAsync({ category, monthlyLimit: newLimit });
        setEditingCategory(null);
        setEditValues({});
      } catch (err) {
        console.error('Failed to update budget:', err);
      }
    }
  };

  const handleCancel = () => {
    setEditingCategory(null);
    setEditValues({});
  };

  return (
    <div className="space-y-4 sm:space-y-6">
      <div>
        <h2 className="text-base sm:text-lg font-semibold text-slate-800">Budget</h2>
        {data?.month && <p className="text-xs sm:text-sm text-slate-500 mt-1">{data.month}</p>}
      </div>

      {budgetItems.length === 0 ? (
        <div className="rounded-md bg-slate-50 p-6 text-center text-slate-500">No budget data available.</div>
      ) : (
        <div className="space-y-4">
          {budgetItems.map((item) => (
            <BudgetItemRow
              key={item.category}
              item={item}
              isEditing={editingCategory === item.category}
              editValue={editValues[item.category]}
              isLoading={upsertMutation.isPending}
              onEdit={() => handleEdit(item.category, item.limit)}
              onSave={() => handleSave(item.category)}
              onCancel={handleCancel}
              onValueChange={(value) => setEditValues({ ...editValues, [item.category]: value })}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface BudgetItemRowProps {
  item: BudgetItem;
  isEditing: boolean;
  editValue?: number;
  isLoading: boolean;
  onEdit: () => void;
  onSave: () => void;
  onCancel: () => void;
  onValueChange: (value: number) => void;
}

function BudgetItemRow({
  item,
  isEditing,
  editValue,
  isLoading,
  onEdit,
  onSave,
  onCancel,
  onValueChange,
}: BudgetItemRowProps) {
  const progressPercent = item.limit ? Math.min((item.spent / item.limit) * 100, 100) : 0;
  const isOver = item.is_over_budget;
  const displayPct = item.pct ? Math.round(item.pct * 100) : 0;

  return (
    <div
      className={`rounded-lg border p-3 sm:p-4 ${isOver ? 'border-red-200 bg-red-50' : 'border-slate-200 bg-white'}`}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex-1 min-w-0">
          <h3 className="font-medium text-sm sm:text-base text-slate-900 break-words">{item.category}</h3>

          {isEditing ? (
            <div className="mt-3 space-y-2">
              <label className="block text-xs sm:text-sm text-slate-600">Monthly Limit</label>
              <input
                type="number"
                value={editValue ?? 0}
                onChange={(e) => onValueChange(parseFloat(e.target.value) || 0)}
                className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 min-h-10"
                disabled={isLoading}
              />
            </div>
          ) : (
            <div className="mt-2 space-y-1">
              <div className="text-xs sm:text-sm text-slate-600">
                Spent: <span className="font-semibold text-slate-900">${item.spent.toFixed(2)}</span>
                {item.limit && <> / ${item.limit.toFixed(2)}</>}
              </div>
              {item.is_current_month && item.projected_eom !== null && (
                <div className="text-xs text-slate-500">
                  Projected end-of-month: ${item.projected_eom.toFixed(2)}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex flex-col items-end gap-2 sm:gap-4 w-full sm:w-auto">
          {!isEditing && item.limit && (
            <div className="w-full sm:w-40 text-right">
              <div className="relative h-2 w-full bg-slate-200 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all duration-300 ${isOver ? 'bg-red-500' : 'bg-green-500'}`}
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <div className="mt-1 text-xs text-slate-600">{displayPct}% of limit</div>
            </div>
          )}

          <div className="flex gap-2 w-full sm:w-auto">
            {isEditing ? (
              <>
                <button
                  onClick={onSave}
                  disabled={isLoading}
                  className="flex-1 sm:flex-auto px-3 py-2 bg-blue-500 text-white text-xs sm:text-sm rounded-md hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors min-h-10 font-medium"
                >
                  {isLoading ? 'Saving...' : 'Save'}
                </button>
                <button
                  onClick={onCancel}
                  disabled={isLoading}
                  className="flex-1 sm:flex-auto px-3 py-2 bg-slate-200 text-slate-700 text-xs sm:text-sm rounded-md hover:bg-slate-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors min-h-10 font-medium"
                >
                  Cancel
                </button>
              </>
            ) : (
              <button
                onClick={onEdit}
                className="flex-1 sm:flex-auto px-3 py-2 bg-slate-200 text-slate-700 text-xs sm:text-sm rounded-md hover:bg-slate-300 transition-colors min-h-10 font-medium"
              >
                Edit
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
