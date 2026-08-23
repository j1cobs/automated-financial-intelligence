import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
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
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white px-6 py-4">
        <p className="text-sm text-slate-600">Signed in as {user?.email}</p>
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
      <main className="p-6">
        {activeTab === 'overview' && <OverviewTab />}
        {activeTab === 'cashflow' && <CashFlowTab />}
        {activeTab === 'budget' && <BudgetTab />}
        {activeTab === 'transactions' && <TransactionsTab />}
      </main>
    </div>
  );
}
