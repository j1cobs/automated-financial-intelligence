/** Shared tab identifiers -- lives outside Dashboard.tsx so HomeTab.tsx can
 *  type its drill-down navigation callback without importing the component
 *  that renders it (would create a module cycle: Dashboard imports HomeTab). */
export type TabId = 'home' | 'overview' | 'cashflow' | 'budget' | 'transactions';
