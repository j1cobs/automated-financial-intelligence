/**
 * Budget tab — per-category spend vs. limit, projected end-of-month.
 * Uses `useBudget()` from `lib/queries.ts` (returns `BudgetResponse` from
 * `lib/types.ts`) and `useUpsertBudget()` from `lib/mutations.ts` for editing limits.
 *
 * The editor lists *every* canonical category, not just the ones with spend or an
 * existing limit (PLAN.md Phase 15, Fix 10 audit). `api/viewmodels.py`'s
 * `build_budget` only returns `period_expenses ∪ budget_map`, so a category with
 * neither would never be offered here. This file closes that gap by merging in
 * `useCategories()` (GET /categories, the canonical list) client-side, rather
 * than requesting an API change.
 *
 * Per-category trend sparklines (Fix 12) reuse `category_distribution` from
 * `useCashFlow()` (GET /cash-flow) — the per-category-per-month spend series
 * already computed there under the same active filters. No new endpoint.
 */

import { useMemo, useState } from 'react';
import { LineChart, Line, ResponsiveContainer } from 'recharts';
import { useBudget, useCategories, useCashFlow, useAnomalies } from '../lib/queries';
import { useUpsertBudget } from '../lib/mutations';
import type { BudgetItem } from '../lib/types';
import { LINE_PROPS, inkMutedColor, negativeColor, useChartTheme } from './chartTheme';
import { TabSkeleton, ErrorState } from './LoadingState';
import { DIRECTION_GLYPH, type Tone } from '../lib/polarity';
import { formatCategory } from '../lib/categories';
import { Button } from '../components/Button';
import { GoalsSection } from './GoalsSection';
import { ForecastChart } from './ForecastChart';

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
function emptyItem(category: string, isCurrentMonth: boolean, period: string | null): BudgetItem {
  return {
    category,
    spent: 0,
    // `null`, not 0: this category has no budget set, which is a different
    // state from being budgeted to spend nothing.
    limit: null,
    pct: null,
    is_over_budget: false,
    projected_eom: null,
    is_current_month: isCurrentMonth,
    period,
    is_inherited: false,
    inherited_from: null,

    details: [],
  };
}

/** 'YYYY-MM' for the current calendar month, in local time. */
function currentMonthKey(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

/** Step a 'YYYY-MM' key by whole months, wrapping across the year boundary. */
function shiftMonth(key: string, delta: number): string {
  const [year, month] = key.split('-').map(Number);
  // Month is 0-indexed here, so `month - 1 + delta` lets Date normalise the
  // year rollover for us rather than doing modular arithmetic by hand.
  const shifted = new Date(year, month - 1 + delta, 1);
  return `${shifted.getFullYear()}-${String(shifted.getMonth() + 1).padStart(2, '0')}`;
}

function formatMonth(key: string): string {
  const [year, month] = key.split('-').map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString('en-US', {
    month: 'long',
    year: 'numeric',
  });
}

export function BudgetTab() {
  const [month, setMonth] = useState<string>(currentMonthKey);
  const { data, isPending, error, refetch } = useBudget(month);
  // Phase 34: category drift is shown on the Budget row it concerns, next to
  // the cap it is about, rather than only on a separate surface.
  const { data: anomalyData } = useAnomalies(month);
  const { data: categoriesData } = useCategories();
  const { data: cashFlow } = useCashFlow();
  const upsertMutation = useUpsertBudget();
  const [editingCategory, setEditingCategory] = useState<string | null>(null);
  const [editValues, setEditValues] = useState<Record<string, number>>({});
  const [expanded, setExpanded] = useState<string | null>(null);
  useChartTheme(); // re-render sparklines when the theme flips

  const budgetItems = useMemo(() => data?.items ?? [], [data]);
  const isCurrentMonth = budgetItems[0]?.is_current_month ?? false;
  const period = data?.month ?? null;

  // Canonical categories (GET /categories) ∪ whatever the budget response already
  // covers — a defensive union in case a category with a stored budget limit was
  // since retired from the canonical list. Sorted, so rows render alphabetically.
  const allItems = useMemo(() => {
    const byCategory = new Map(budgetItems.map((item) => [item.category, item]));
    const names = new Set<string>([...(categoriesData?.categories ?? []), ...byCategory.keys()]);
    return Array.from(names)
      .sort((a, b) => a.localeCompare(b))
      .map((cat) => byCategory.get(cat) ?? emptyItem(cat, isCurrentMonth, period));
  }, [budgetItems, categoriesData, isCurrentMonth, period]);

  const driftByCategory = useMemo(() => {
    const map = new Map<string, string>();
    for (const anomaly of anomalyData?.anomalies ?? []) {
      if (anomaly.kind === 'category_drift') map.set(anomaly.subject, anomaly.explanation);
    }
    return map;
  }, [anomalyData]);

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
        // Always names the displayed month: editing an inherited cap writes an
        // explicit row here and leaves every other month alone.
        await upsertMutation.mutateAsync({ category, monthlyLimit: newLimit, month });
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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base sm:text-lg font-semibold text-ink">Budget</h2>
          <p className="mt-1 text-xs text-ink-muted sm:text-sm">{formatMonth(month)}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={() => setMonth((current) => shiftMonth(current, -1))}
            aria-label="Previous month"
          >
            Previous
          </Button>
          <Button
            size="sm"
            onClick={() => setMonth(currentMonthKey())}
            disabled={month === currentMonthKey()}
          >
            This month
          </Button>
          <Button
            size="sm"
            onClick={() => setMonth((current) => shiftMonth(current, 1))}
            aria-label="Next month"
          >
            Next
          </Button>
        </div>
      </div>

      <ForecastChart />

      <GoalsSection />

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
              drift={driftByCategory.get(item.category) ?? null}
              isExpanded={expanded === item.category}
              onToggleExpand={() =>
                setExpanded((current) => (current === item.category ? null : item.category))
              }
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
  /** The drift explanation for this category this month, if any. */
  drift: string | null;
  isExpanded: boolean;
  onToggleExpand: () => void;
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
  drift,
  isExpanded,
  onToggleExpand,
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
            {/* An inherited cap was never set for this month -- say so, and say
                where it came from, rather than presenting it as a decision made
                here. Editing it writes an explicit row for this month only. */}
            {item.is_inherited && item.inherited_from && (
              <span className="text-ink-muted"> · inherited from {formatMonth(item.inherited_from)}</span>
            )}
          </div>
        )}

        {drift && !isEditing && <p className="mt-1 text-xs text-neg-text">{drift}</p>}

        {item.details.length > 0 && !isEditing && (
          <div className="mt-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={onToggleExpand}
              aria-expanded={isExpanded}
              className="min-h-0 px-0 py-0"
            >
              {isExpanded ? 'Hide breakdown' : `Breakdown (${item.details.length})`}
            </Button>
            {isExpanded && (
              <ul className="mt-1 space-y-0.5 border-l border-hairline pl-3">
                {item.details.map((detail) => (
                  <li
                    key={detail.pfc_detailed ?? '__none__'}
                    className="flex justify-between gap-4 text-xs text-ink-secondary tabular-nums"
                  >
                    <span className="truncate">
                      {detail.pfc_detailed ? formatCategory(detail.pfc_detailed) : 'Unspecified'}
                    </span>
                    <span className="shrink-0">{money(detail.amount)}</span>
                  </li>
                ))}
              </ul>
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
            <Button variant="primary" onClick={onSave} disabled={isLoading} className="flex-1 sm:flex-auto">
              {isLoading ? 'Saving...' : 'Save'}
            </Button>
            <Button onClick={onCancel} disabled={isLoading} className="flex-1 bg-surface-3 sm:flex-auto">
              Cancel
            </Button>
          </>
        ) : (
          <Button onClick={onEdit} className="flex-1 bg-surface-3 sm:flex-auto">
            Edit
          </Button>
        )}
      </div>
    </div>
  );
}
