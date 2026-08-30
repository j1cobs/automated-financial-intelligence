/** Shared tab identifiers -- lives outside Dashboard.tsx so tabs can
 *  type their drill-down navigation callback without importing the component
 *  that renders them (would create a module cycle: Dashboard imports tabs). */
export type TabId = 'overview' | 'cashflow' | 'budget' | 'transactions';
