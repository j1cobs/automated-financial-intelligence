import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useTheme, type ThemePreference } from '../lib/useTheme';
import { FilterProvider } from '../lib/FilterContext';
import { FilterBar } from './FilterBar';
import { OverviewTab } from './OverviewTab';
import { CashFlowTab } from './CashFlowTab';
import { BudgetTab } from './BudgetTab';
import { TransactionsTab } from './TransactionsTab';

type TabId = 'overview' | 'cashflow' | 'budget' | 'transactions';

const TABS: { id: TabId; label: string }[] = [
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
 * Authenticated dashboard shell: header + 4-tab layout (Overview, Cash Flow,
 * Budget, Transactions). Tab switching is local `useState` — no router, same
 * decision R3 made for the auth flow. Each tab is a self-contained component
 * in this directory; adding a 5th tab means adding it to `TABS` and the
 * switch below, nothing else in this file needs to change per-tab.
 */
export function Dashboard() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<TabId>('overview');

  return (
    <FilterProvider>
      <div className="min-h-screen bg-slate-50">
        <header className="flex items-center justify-between gap-4 border-b border-slate-200 bg-white px-6 py-4">
          <p className="text-sm text-slate-600">Signed in as {user?.email}</p>
          <ThemeToggle />
        </header>
        <nav className="border-b border-slate-200 bg-white px-3 sm:px-6">
          <div className="flex gap-2 sm:gap-4 overflow-x-auto">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                aria-current={activeTab === tab.id ? 'page' : undefined}
                className={`border-b-2 px-2 sm:px-2 py-3 sm:py-3 text-xs sm:text-sm font-medium transition-colors min-h-11 flex items-center whitespace-nowrap ${
                  activeTab === tab.id
                    ? 'border-slate-800 text-slate-900'
                    : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </nav>
        <FilterBar />
        <main className="p-6">
          {activeTab === 'overview' && <OverviewTab />}
          {activeTab === 'cashflow' && <CashFlowTab />}
          {activeTab === 'budget' && <BudgetTab />}
          {activeTab === 'transactions' && <TransactionsTab />}
        </main>
      </div>
    </FilterProvider>
  );
}
