import { useOverview } from '../lib/queries';
import type { PieLabelRenderProps } from 'recharts';
import {
  LineChart,
  Line,
  PieChart,
  Pie,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from 'recharts';

const COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function StatTile({
  label,
  value,
  format = 'currency',
}: {
  label: string;
  value: number;
  format?: 'currency' | 'percent' | 'number';
}) {
  let formatted: string;
  if (format === 'currency') {
    formatted = formatCurrency(value);
  } else if (format === 'percent') {
    formatted = formatPercent(value);
  } else {
    formatted = value.toLocaleString();
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 sm:p-4">
      <p className="text-xs sm:text-sm font-medium text-slate-600">{label}</p>
      <p className="mt-2 text-xl sm:text-2xl font-bold text-slate-900">{formatted}</p>
    </div>
  );
}

export function OverviewTab() {
  const { data, isLoading, error } = useOverview();

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-slate-200 border-t-blue-500"></div>
        <p className="mt-4 text-slate-600">Loading overview...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6">
        <h3 className="text-lg font-semibold text-red-900">Error loading overview</h3>
        <p className="mt-2 text-red-700">
          {error instanceof Error ? error.message : 'An unexpected error occurred'}
        </p>
      </div>
    );
  }

  if (!data?.net_worth || !data?.overview) {
    return (
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-6">
        <p className="text-slate-600">No data available</p>
      </div>
    );
  }

  const nw = data.net_worth;
  const ov = data.overview;

  return (
    <div className="space-y-6">
      {/* KPI Tiles */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Net Worth" value={nw.net_worth} />
        <StatTile label="Total Assets" value={nw.total_assets} />
        <StatTile label="Total Liabilities" value={nw.total_liabilities} />
        <StatTile label="Savings Rate" value={ov.savings_rate} format="percent" />
      </div>

      {/* Income and Expenses Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatTile label="Monthly Income" value={ov.avg_monthly_income} />
        <StatTile label="Monthly Expenses" value={ov.avg_monthly_expense} />
        <StatTile label="Net Monthly Flow" value={ov.net_flow} />
      </div>

      {/* Savings Rate Trend Chart */}
      {ov?.savings_rate_trend && ov.savings_rate_trend.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-3 sm:p-6">
          <h3 className="mb-4 text-base sm:text-lg font-semibold text-slate-900">Savings Rate Trend</h3>
          <ResponsiveContainer width="100%" height={250} minWidth="100%">
            <LineChart data={ov.savings_rate_trend}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" />
              <YAxis tickFormatter={(value) => formatPercent(value)} domain={[0, 1]} />
              <Tooltip formatter={(value) => formatPercent(value as number)} labelStyle={{ color: '#000' }} />
              <Line
                type="monotone"
                dataKey="savings_rate"
                stroke="#3b82f6"
                strokeWidth={2}
                dot={{ fill: '#3b82f6' }}
                name="Savings Rate"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Asset Mix and Owner Balances */}
      <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
        {/* Asset Mix Pie Chart */}
        {nw?.asset_mix && nw.asset_mix.length > 0 && (
          <div className="rounded-lg border border-slate-200 bg-white p-3 sm:p-6">
            <h3 className="mb-4 text-base sm:text-lg font-semibold text-slate-900">Asset Mix</h3>
            <ResponsiveContainer width="100%" height={250} minWidth="100%">
              <PieChart>
                <Pie
                  data={nw.asset_mix}
                  dataKey="balance"
                  nameKey="subtype_label"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  label={(props: PieLabelRenderProps) => {
                    const entry = props.payload as unknown as { subtype_label: string; percent?: number };
                    const percent = (props as unknown as { percent?: number }).percent ?? 0;
                    return `${entry.subtype_label} ${(percent * 100).toFixed(0)}%`;
                  }}
                >
                  {nw.asset_mix.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value) => formatCurrency(value as number)} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Owner Balances Bar Chart */}
        {nw?.owner_balances && nw.owner_balances.length > 0 && (
          <div className="rounded-lg border border-slate-200 bg-white p-3 sm:p-6">
            <h3 className="mb-4 text-base sm:text-lg font-semibold text-slate-900">Owner Balances</h3>
            <ResponsiveContainer width="100%" height={250} minWidth="100%">
              <BarChart data={nw.owner_balances}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="owner" />
                <YAxis tickFormatter={(value) => formatCurrency(value)} />
                <Tooltip formatter={(value) => formatCurrency(value as number)} />
                <Legend />
                <Bar dataKey="value" fill="#10b981" name="Balance" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Top Categories */}
      {ov?.top_categories && ov.top_categories.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-3 sm:p-6">
          <h3 className="mb-4 text-base sm:text-lg font-semibold text-slate-900">Top Expense Categories</h3>
          <ResponsiveContainer width="100%" height={250} minWidth="100%">
            <BarChart data={ov.top_categories}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="category" />
              <YAxis tickFormatter={(value) => formatCurrency(value)} />
              <Tooltip formatter={(value) => formatCurrency(value as number)} />
              <Bar dataKey="amount" fill="#f59e0b" name="Amount" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Additional Metrics */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {ov.emergency_fund_months !== null && (
          <StatTile label="Emergency Fund Months" value={ov.emergency_fund_months} format="number" />
        )}
        <StatTile label="Flagged Transactions" value={ov.flagged_count} format="number" />
        {ov.avg_weekly_expense > 0 && <StatTile label="Weekly Expenses" value={ov.avg_weekly_expense} />}
      </div>

      {/* Stale Accounts Warning */}
      {nw?.stale_accounts && nw.stale_accounts.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 sm:p-6">
          <h3 className="font-semibold text-sm sm:text-base text-amber-900">Stale Accounts</h3>
          <div className="mt-2 space-y-1">
            {nw.stale_accounts.map((account) => (
              <p key={account.account_name} className="text-sm text-amber-800">
                {account.account_name} — {account.days_stale} days without activity
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
