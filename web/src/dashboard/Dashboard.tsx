import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useTheme, type ThemePreference } from '../lib/useTheme';
import { FilterProvider, useFilters } from '../lib/FilterContext';
import { formatDateRangeLabel, type DashboardFilters } from '../lib/filters';
import { monthsCoveringRange } from '../lib/dateRanges';
import { FilterBar } from './FilterBar';
import { HomeTab } from './HomeTab';
import { OverviewTab } from './OverviewTab';
import { CashFlowTab } from './CashFlowTab';
import { BudgetTab } from './BudgetTab';
import { TransactionsTab } from './TransactionsTab';
import type { TabId } from './tabs';

const TABS: { id: TabId; label: string }[] = [
  { id: 'home', label: 'Home' },
  { id: 'overview', label: 'Overview' },
  { id: 'cashflow', label: 'Cash Flow' },
  { id: 'budget', label: 'Budget' },
  { id: 'transactions', label: 'Transactions' },
];

const THEME_OPTIONS: { id: ThemePreference; label: string; glyph: string }[] = [
  { id: 'system', label: 'Match system theme', glyph: 'Auto' },
  { id: 'light', label: 'Light theme', glyph: 'Light' },
  { id: 'dark', label: 'Dark theme', glyph: 'Dark' },
];

/**
 * Three-state theme control (system / light / dark). It writes one attribute on
 * `<html>`; every colour on the page follows from the token layer in
 * `src/index.css`, so there is no per-component dark branch anywhere.
 */
function ThemeToggle() {
  const { preference, setTheme } = useTheme();

  return (
    <div
      role="group"
      aria-label="Theme"
      className="flex items-center gap-0.5 rounded-md border border-[var(--border-hairline)] p-0.5"
    >
      {THEME_OPTIONS.map((option) => (
        <button
          key={option.id}
          type="button"
          onClick={() => setTheme(option.id)}
          aria-label={option.label}
          aria-pressed={preference === option.id}
          className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
            preference === option.id
              ? 'bg-[var(--surface-3)] text-[var(--text-primary)]'
              : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'
          }`}
        >
          {option.glyph}
        </button>
      ))}
    </div>
  );
}

/**
 * Authenticated dashboard shell: header + 5-tab layout (Home, Overview, Cash
 * Flow, Budget, Transactions). Home is the default landing tab -- a
 * daily-check-in status surface (PLAN.md §4 Q1/Q2); the other four are
 * untouched and serve as its "go deeper" drill-down layer. Tab switching is
 * local `useState` — no router, same decision R3 made for the auth flow.
 * Each tab is a self-contained component in this directory; adding another
 * tab means adding it to `TABS` and the switch below, nothing else in this
 * file needs to change per-tab.
 *
 * Thin wrapper around `DashboardShell`: `<FilterProvider>` wraps what this
 * function *returns*, not its own body, so `Dashboard()` itself cannot call
 * `useFilters()` -- that context is only reachable from a component actually
 * rendered as `FilterProvider`'s child. The drill-down snapshot/restore state
 * needs `useFilters()`, so it lives in `DashboardShell`, one level inside the
 * provider.
 */
export function Dashboard() {
  return (
    <FilterProvider>
      <DashboardShell />
    </FilterProvider>
  );
}

/** Snapshot of "where the user was" before a cross-tab drill-down, so a single
 *  "Back" action can restore it. Deliberately one level, not a history stack
 *  -- the only requirement is "come back to where I was", and a stack would
 *  be over-engineering for that. */
interface ReturnSnapshot {
  tab: TabId;
  filters: DashboardFilters;
}

function DashboardShell() {
  const { user } = useAuth();
  const { filters, setFilters, patchFilters } = useFilters();
  const [activeTab, setActiveTab] = useState<TabId>('home');
  const [returnTo, setReturnTo] = useState<ReturnSnapshot | null>(null);

  // Any manual tab change (the nav buttons, or Home's own onNavigate) clears
  // a pending return snapshot -- otherwise a stale "Back to Cash Flow" button
  // could linger on a tab the user reached some other way.
  function goToTab(tab: TabId) {
    setReturnTo(null);
    setActiveTab(tab);
  }

  // Rolling-30-day-spend point click (CashFlowTab) -> Transactions, filtered
  // to that exact 30-day window. Captures the pre-drill-down tab + filters
  // first, so "Back to Cash Flow" can restore them exactly.
  function handleDrillDownToTransactions(dateFrom: string, dateTo: string) {
    setReturnTo({ tab: activeTab, filters });
    patchFilters({
      period: 'custom',
      months: monthsCoveringRange(dateFrom, dateTo),
      date_from: dateFrom,
      date_to: dateTo,
    });
    setActiveTab('transactions');
  }

  // "Back to Cash Flow" (TransactionsTab). A full restore, not a patch:
  // `patchFilters` only merges partial changes, so it could leave behind a
  // filter axis the drill-down added but the pre-drill-down state didn't
  // have -- `setFilters` replaces the whole object instead.
  function handleReturn() {
    if (!returnTo) return;
    setFilters(returnTo.filters);
    setActiveTab(returnTo.tab);
    setReturnTo(null);
  }

  return (
    <div className="min-h-screen bg-surface-page">
      <header className="flex items-center justify-between gap-4 border-b border-hairline bg-surface-1 px-6 py-4">
        <p className="text-sm text-ink-secondary">Signed in as {user?.email}</p>
        <ThemeToggle />
      </header>
      <nav className="border-b border-hairline bg-surface-1 px-3 sm:px-6">
        <div className="flex gap-2 sm:gap-4 overflow-x-auto">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => goToTab(tab.id)}
              aria-current={activeTab === tab.id ? 'page' : undefined}
              className={`border-b-2 px-2 sm:px-2 py-3 sm:py-3 text-xs sm:text-sm font-medium transition-colors min-h-11 flex items-center whitespace-nowrap ${
                activeTab === tab.id
                  ? 'border-ink text-ink'
                  : 'border-transparent text-ink-muted hover:text-ink-secondary'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </nav>
      <FilterBar />
      <main className="p-6">
        {activeTab === 'home' && <HomeTab onNavigate={goToTab} />}
        {activeTab === 'overview' && <OverviewTab />}
        {activeTab === 'cashflow' && (
          <CashFlowTab onDrillDownToTransactions={handleDrillDownToTransactions} />
        )}
        {activeTab === 'budget' && <BudgetTab />}
        {activeTab === 'transactions' && (
          <TransactionsTab
            returnTo={
              returnTo
                ? {
                    tab: returnTo.tab,
                    // Widens the snapshot passed down for display only (Item 3) --
                    // the restore mechanism above still snapshots/restores the
                    // whole `DashboardFilters` object, this is just a label.
                    dateRangeLabel:
                      returnTo.filters.date_from && returnTo.filters.date_to
                        ? formatDateRangeLabel(returnTo.filters.date_from, returnTo.filters.date_to)
                        : null,
                  }
                : null
            }
            onReturn={handleReturn}
          />
        )}
      </main>
    </div>
  );
}
