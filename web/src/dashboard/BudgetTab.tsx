/**
 * Budget tab — per-category spend vs. limit, projected end-of-month.
 * Uses `useBudget()` from `lib/queries.ts` (returns `BudgetResponse` from
 * `lib/types.ts`) and `useUpsertBudget()` from `lib/mutations.ts` for editing limits.
 *
 * Port of `_section_budget` (`app/dashboard.py:1110-1188`), with one deliberate
 * capability fix over the first React port (PLAN.md Phase 15, Fix 10 audit):
 * Streamlit's editor lists *every* canonical category (`db.get_categories()`),
 * not just the ones with spend or an existing limit, because `_section_budget`
 * builds its editor list from a second, separate query. `api/viewmodels.py`'s
 * `build_budget` only returns `period_expenses ∪ budget_map` — a category with
 * neither could never be offered here. This file closes that gap by merging in
 * `useCategories()` (GET /categories, the canonical list) client-side, rather
 * than requesting an API change.
 *
 * Per-category trend sparklines (Fix 12) reuse `category_distribution` from
 * `useCashFlow()` (GET /cash-flow) — the per-category-per-month spend series
 * already computed there under the same active filters. No new endpoint.
 */

import { useMemo, useState } from 'react';
import { LineChart, Line, ResponsiveContainer } from 'recharts';
import { useBudget, useCategories, useCashFlow } from '../lib/queries';
import { useUpsertBudget } from '../lib/mutations';
import type { BudgetItem } from '../lib/types';
import { LINE_PROPS, inkMutedColor, negativeColor, useChartTheme } from './chartTheme';
import { TabSkeleton, ErrorState } from './LoadingState';
import { DIRECTION_GLYPH, type Tone } from '../lib/polarity';
import { formatCategory } from '../lib/categories';

/** How many trailing months the per-category sparkline shows. */
const SPARKLINE_MONTHS = 6;

function money(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

/** A category with no API row yet (no spend, no limit) — still offered for editing. */
function emptyItem(category: string, isCurrentMonth: boolean): BudgetItem {
  return {
    category,
    spent: 0,
    limit: null,
    pct: null,
    is_over_budget: false,
    projected_eom: null,
    is_current_month: isCurrentMonth,
  };
}

export function BudgetTab() {
  const { data, isPending, error, refetch } = useBudget();
  const { data: categoriesData } = useCategories();
  const { data: cashFlow } = useCashFlow();
  const upsertMutation = useUpsertBudget();
  const [editingCategory, setEditingCategory] = useState<string | null>(null);
  const [editValues, setEditValues] = useState<Record<string, number>>({});
  useChartTheme(); // re-render sparklines when the theme flips

  const budgetItems = useMemo(() => data?.items ?? [], [data]);
  const isCurrentMonth = budgetItems[0]?.is_current_month ?? false;

  // Canonical categories (GET /categories) ∪ whatever the budget response already
  // covers — a defensive union in case a category with a stored budget limit was
  // since retired from the canonical list. Sorted, matching Streamlit's
  // `sorted(set(...) | set(...))`.
  const allItems = useMemo(() => {
    const byCategory = new Map(budgetItems.map((item) => [item.category, item]));
    const names = new Set<string>([...(categoriesData?.categories ?? []), ...byCategory.keys()]);
    return Array.from(names)
      .sort((a, b) => a.localeCompare(b))
      .map((cat) => byCategory.get(cat) ?? emptyItem(cat, isCurrentMonth));
  }, [budgetItems, categoriesData, isCurrentMonth]);

  const trendByCategory = useMemo(() => {
    const map = new Map<string, { month: string; amount: number }[]>();
    for (const row of cashFlow?.category_distribution ?? []) {
      const arr = map.get(row.category);
      if (arr) arr.push({ month: row.month, amount: row.amount });
      else map.set(row.category, [{ month: row.month, amount: row.amount }]);
    }
    for (const arr of map.values()) arr.sort((a, b) => a.month.localeCompare(b.month));
    return map;
  }, [cashFlow]);

  if (isPending) {
    return <TabSkeleton />;
  }

  if (error) {
    return (
      <div className="space-y-4">
        <h2 className="text-base sm:text-lg font-semibold text-ink">Budget</h2>
        <ErrorState message="Failed to load budget data. Please try again." onRetry={() => void refetch()} />
      </div>
    );
  }

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
        <h2 className="text-base sm:text-lg font-semibold text-ink">Budget</h2>
        {data?.month && <p className="text-xs sm:text-sm text-ink-muted mt-1">{data.month}</p>}
      </div>

      {allItems.length === 0 ? (
        <div className="rounded-md bg-surface-2 p-6 text-center text-ink-muted">
          No budget data available.
        </div>
      ) : (
        <div className="divide-y divide-hairline rounded-lg border border-hairline bg-surface-1">
          {allItems.map((item) => (
            <BudgetItemRow
              key={item.category}
              item={item}
              trend={(trendByCategory.get(item.category) ?? []).slice(-SPARKLINE_MONTHS)}
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
  trend: { month: string; amount: number }[];
  isEditing: boolean;
  editValue?: number;
  isLoading: boolean;
  onEdit: () => void;
  onSave: () => void;
  onCancel: () => void;
  onValueChange: (value: number) => void;
}

/** Status badge — glyph + label, never colour alone (see `DIRECTION_GLYPH` / polarity.ts). */
function statusBadge(item: BudgetItem): { tone: Tone; glyph: string; label: string } {
  if (item.limit == null) {
    return { tone: 'neutral', glyph: DIRECTION_GLYPH.flat, label: 'No budget set' };
  }
  if (item.is_over_budget) {
    return { tone: 'bad', glyph: DIRECTION_GLYPH.up, label: 'Over budget' };
  }
  return { tone: 'good', glyph: DIRECTION_GLYPH.down, label: 'On track' };
}

function BudgetItemRow({
  item,
  trend,
  isEditing,
  editValue,
  isLoading,
  onEdit,
  onSave,
  onCancel,
  onValueChange,
}: BudgetItemRowProps) {
  const progressPercent = item.pct != null ? Math.min(item.pct * 100, 100) : 0;
  const isOver = item.is_over_budget;
  const displayPct = item.pct != null ? Math.round(item.pct * 100) : null;
  const badge = statusBadge(item);
  const toneClasses: Record<Tone, string> = {
    good: 'text-pos-text',
    bad: 'text-neg-text',
    neutral: 'text-ink-muted',
  };
  const barClasses: Record<Tone, string> = {
    good: 'bg-pos',
    bad: 'bg-neg',
    neutral: 'bg-neutral',
  };

  return (
    <div
      className={`flex flex-col gap-2 border-l-4 p-3 sm:flex-row sm:items-center sm:gap-4 sm:p-3 ${
        isOver ? 'border-l-[var(--neg)]' : 'border-l-transparent'
      }`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <h3 className="font-medium text-sm text-ink break-words">{formatCategory(item.category)}</h3>
          <span
            className={`inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide ${toneClasses[badge.tone]}`}
          >
            <span aria-hidden="true">{badge.glyph}</span>
            {badge.label}
          </span>
        </div>

        {isEditing ? (
          <div className="mt-2 flex items-center gap-2">
            <label className="text-xs text-ink-secondary" htmlFor={`budget-limit-${item.category}`}>
              Monthly limit
            </label>
            <input
              id={`budget-limit-${item.category}`}
              type="number"
              value={editValue ?? 0}
              onChange={(e) => onValueChange(parseFloat(e.target.value) || 0)}
              className="w-28 min-h-9 rounded-md border border-strong bg-surface-1 px-2 py-1 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-cat-1"
              disabled={isLoading}
            />
          </div>
        ) : (
          <div className="mt-1 text-xs sm:text-sm text-ink-secondary tabular-nums">
            {money(item.spent)}
            {item.limit != null && <> / {money(item.limit)}</>}
            {displayPct != null && <span className="text-ink-muted"> — {displayPct}% of limit</span>}
            {item.limit == null && <span className="text-ink-muted"> (no budget set)</span>}
            {item.is_current_month && item.projected_eom !== null ? (
              <span className="text-ink-muted"> · Projected EOM: {money(item.projected_eom)}</span>
            ) : (
              !item.is_current_month && <span className="text-ink-muted"> · Actual: {money(item.spent)}</span>
            )}
          </div>
        )}
      </div>

      {!isEditing && (
        <div className="h-6 w-16 shrink-0" aria-hidden={trend.length < 2}>
          {trend.length >= 2 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trend}>
                <Line {...LINE_PROPS} dataKey="amount" stroke={isOver ? negativeColor() : inkMutedColor()} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <span className="text-[10px] text-ink-muted">No trend</span>
          )}
        </div>
      )}

      {!isEditing && item.limit != null && (
        <div className="w-full shrink-0 sm:w-28">
          <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-surface-3">
            <div
              className={`h-full transition-all duration-300 ${barClasses[badge.tone]}`}
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      )}

      <div className="flex gap-2 sm:w-auto">
        {isEditing ? (
          <>
            <button
              onClick={onSave}
              disabled={isLoading}
              className="flex-1 sm:flex-auto px-3 py-2 bg-cat-1 text-white text-xs sm:text-sm rounded-md hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity min-h-9 font-medium"
            >
              {isLoading ? 'Saving...' : 'Save'}
            </button>
            <button
              onClick={onCancel}
              disabled={isLoading}
              className="flex-1 sm:flex-auto px-3 py-2 bg-surface-3 text-ink text-xs sm:text-sm rounded-md hover:bg-surface-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors min-h-9 font-medium"
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            onClick={onEdit}
            className="flex-1 sm:flex-auto px-3 py-2 bg-surface-3 text-ink text-xs sm:text-sm rounded-md hover:bg-surface-2 transition-colors min-h-9 font-medium"
          >
            Edit
          </button>
        )}
      </div>
    </div>
  );
}
