/**
 * Savings goals (Phase 33), rendered inside the Budget tab.
 *
 * Generic by design: a down payment, a car and an emergency fund are the same
 * shape. Nothing here knows what the money is for.
 *
 * Two rules this component exists to honour:
 *
 *  - **A pace is never shown without its basis.** `pace_basis` is 'cashflow'
 *    until a goal has twelve weeks of balance snapshots, and the label says so
 *    along with how many weeks back it. A confident-looking number built on
 *    four weeks of history is worse than no number.
 *  - **Contested progress is visible.** Two goals may share an account —
 *    people really do save for two things in one place — but if that went
 *    unsaid the tab would report both on track when the same dollars can only
 *    buy one.
 */

import { useState } from 'react';
import { useGoals } from '../lib/queries';
import { useCreateGoal, useDeleteGoal } from '../lib/mutations';
import type { GoalItem } from '../lib/types';
import { Button } from '../components/Button';

function money(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);
}

function formatDate(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number);
  return new Date(year, month - 1, day).toLocaleDateString('en-US', {
    month: 'short',
    year: 'numeric',
  });
}

/** Plain-language pace, with the provenance it must never be shown without. */
function paceLabel(goal: GoalItem): string {
  const rate = `${money(goal.monthly_pace)}/mo`;
  if (goal.pace_basis === 'balance') {
    return `${rate} — measured from your balances`;
  }
  const weeks = goal.pace_weeks_of_history;
  return `${rate} — from cash flow (${weeks} week${weeks === 1 ? '' : 's'} of balance history so far)`;
}

/** `on_track` is null for two different reasons, and they must not read the
 *  same: either there is no projection (a zero pace), or there IS one but no
 *  target date to judge it against. Conflating them put "No projection yet"
 *  directly above "Projected Mar 2027". */
function statusLabel(goal: GoalItem): string {
  if (goal.is_complete) return 'Reached';
  if (goal.projected_date === null) return 'No projection yet';
  if (goal.on_track === null) return 'No target date';
  return goal.on_track ? 'On track' : 'Behind';
}

export function GoalsSection() {
  const { data, isPending } = useGoals();
  const createGoal = useCreateGoal();
  const deleteGoal = useDeleteGoal();
  const [isAdding, setIsAdding] = useState(false);
  const [draft, setDraft] = useState({ name: '', target: '', date: '' });

  if (isPending) return null;

  const goals = data?.goals ?? [];

  const submit = () => {
    const target = Number.parseFloat(draft.target);
    if (!draft.name.trim() || !Number.isFinite(target) || target <= 0) return;
    createGoal.mutate(
      {
        name: draft.name.trim(),
        target_amount: target,
        target_date: draft.date || null,
        account_keys: [],
      },
      {
        onSuccess: () => {
          setDraft({ name: '', target: '', date: '' });
          setIsAdding(false);
        },
      },
    );
  };

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold text-ink">Goals</h3>
          <p className="text-xs text-ink-muted">
            Anything you are saving toward — a home, a car, an emergency fund.
          </p>
        </div>
        <Button size="sm" onClick={() => setIsAdding((open) => !open)}>
          {isAdding ? 'Cancel' : 'Add goal'}
        </Button>
      </div>

      {isAdding && (
        <div className="flex flex-wrap items-end gap-2 rounded-lg border border-hairline bg-surface-1 p-3">
          <label className="flex flex-col gap-1 text-xs text-ink-secondary">
            Name
            <input
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              className="min-h-9 w-44 rounded-md border border-hairline bg-surface-1 px-2 py-1 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-cat-1"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-ink-secondary">
            Target amount
            <input
              type="number"
              value={draft.target}
              onChange={(event) => setDraft({ ...draft, target: event.target.value })}
              className="min-h-9 w-32 rounded-md border border-hairline bg-surface-1 px-2 py-1 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-cat-1"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-ink-secondary">
            Target date (optional)
            <input
              type="date"
              value={draft.date}
              onChange={(event) => setDraft({ ...draft, date: event.target.value })}
              className="min-h-9 rounded-md border border-hairline bg-surface-1 px-2 py-1 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-cat-1"
            />
          </label>
          <Button variant="primary" onClick={submit} disabled={createGoal.isPending}>
            {createGoal.isPending ? 'Saving…' : 'Create'}
          </Button>
        </div>
      )}

      {goals.length === 0 ? (
        <p className="rounded-lg border border-hairline bg-surface-1 p-4 text-center text-sm text-ink-muted">
          No goals yet.
        </p>
      ) : (
        <ul className="divide-y divide-hairline rounded-lg border border-hairline bg-surface-1">
          {goals.map((goal) => (
            <li key={goal.id} className="p-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-sm font-medium text-ink">{goal.name}</span>
                <span className="text-xs text-ink-secondary">{statusLabel(goal)}</span>
              </div>

              <div className="mt-1 text-xs text-ink-secondary tabular-nums">
                {money(goal.saved)} of {money(goal.target_amount)}
                {goal.pct !== null && (
                  <span className="text-ink-muted"> — {Math.round(goal.pct * 100)}%</span>
                )}
                {goal.target_date && (
                  <span className="text-ink-muted"> · by {formatDate(goal.target_date)}</span>
                )}
              </div>

              <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-surface-3">
                <div
                  className="h-full rounded-full bg-cat-1"
                  style={{ width: `${Math.min(Math.max((goal.pct ?? 0) * 100, 0), 100)}%` }}
                />
              </div>

              <p className="mt-1.5 text-xs text-ink-muted">{paceLabel(goal)}</p>

              {goal.projected_date && (
                <p className="text-xs text-ink-muted">Projected {formatDate(goal.projected_date)}</p>
              )}

              {goal.contested_amount > 0 && (
                <p className="mt-1 text-xs text-neg-text">
                  {money(goal.contested_amount)} of this sits in an account another goal also claims.
                </p>
              )}

              <div className="mt-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="min-h-0 px-0 py-0"
                  disabled={deleteGoal.isPending}
                  onClick={() => deleteGoal.mutate(goal.id)}
                >
                  Remove
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
