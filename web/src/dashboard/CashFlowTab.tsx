import {
  ComposedChart,
  Bar,
  Line,
  LineChart,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { TooltipContentProps } from 'recharts';
import { useCashFlow } from '../lib/queries';
import type { RollingSpendItem } from '../lib/types';

function money(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

/**
 * Shows the 30-day total and the per-day figure it implies. The per-day number is why
 * this tooltip exists: the series used to be labelled "Daily Spend" while plotting a
 * 30-day total, so a ~$7,500 month read as a $7,500 day.
 */
function RollingSpendTooltip({ active, payload, label }: Partial<TooltipContentProps<number, string>>) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }
  const row = payload[0]?.payload as RollingSpendItem | undefined;
  if (!row) {
    return null;
  }
  return (
    <div className="rounded-md border border-slate-200 bg-white p-2 text-xs shadow-sm sm:text-sm">
      <p className="mb-1 font-semibold text-slate-900">{String(label)}</p>
      <p className="text-slate-700">{money(row.amount)} over the previous 30 days</p>
      <p className="text-slate-500">{money(row.daily_avg)} per day on average</p>
    </div>
  );
}

/**
 * Cash Flow tab — monthly/weekly trends, rolling spend, category distribution.
 * Uses `useCashFlow()` from `lib/queries.ts` (returns `CashFlowResponse`
 * from `lib/types.ts`) and Recharts.
 */
export function CashFlowTab() {
  const { data, isLoading, error } = useCashFlow();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-slate-800">Cash Flow</h2>
        <div className="flex items-center justify-center rounded-lg bg-slate-100 py-12">
          <p className="text-sm text-slate-600">Loading cash flow data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-slate-800">Cash Flow</h2>
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-800">Failed to load cash flow data. Please try again later.</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-slate-800">Cash Flow</h2>
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm text-slate-600">No cash flow data available.</p>
        </div>
      </div>
    );
  }

  // Format currency
  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  // Format percentage
  const formatPercent = (value: number) => {
    return `${(value * 100).toFixed(1)}%`;
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-800">Cash Flow</h2>
      </div>

      {/* Key metrics stat tiles */}
      <div className="grid grid-cols-2 gap-2 sm:gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {/* Income */}
        <div className="rounded-lg border border-slate-200 bg-white p-3 sm:p-4">
          <p className="text-xs sm:text-sm font-medium text-slate-600">Total Income</p>
          <p className="mt-1 sm:mt-2 text-lg sm:text-2xl font-bold text-green-600">
            {formatCurrency(data.income)}
          </p>
        </div>

        {/* Expenses */}
        <div className="rounded-lg border border-slate-200 bg-white p-3 sm:p-4">
          <p className="text-xs sm:text-sm font-medium text-slate-600">Total Expenses</p>
          <p className="mt-1 sm:mt-2 text-lg sm:text-2xl font-bold text-red-600">
            {formatCurrency(data.expenses)}
          </p>
        </div>

        {/* Net Flow */}
        <div className="rounded-lg border border-slate-200 bg-white p-3 sm:p-4">
          <p className="text-xs sm:text-sm font-medium text-slate-600">Net Flow</p>
          <p
            className={`mt-1 sm:mt-2 text-lg sm:text-2xl font-bold ${data.net_flow >= 0 ? 'text-green-600' : 'text-red-600'}`}
          >
            {formatCurrency(data.net_flow)}
          </p>
        </div>

        {/* Savings Rate */}
        <div className="rounded-lg border border-slate-200 bg-white p-3 sm:p-4">
          <p className="text-xs sm:text-sm font-medium text-slate-600">Savings Rate</p>
          <p className="mt-1 sm:mt-2 text-lg sm:text-2xl font-bold text-blue-600">
            {formatPercent(data.savings_rate)}
          </p>
        </div>

        {/* Transfers */}
        <div className="rounded-lg border border-slate-200 bg-white p-3 sm:p-4">
          <p className="text-xs sm:text-sm font-medium text-slate-600">Transfers</p>
          <p className="mt-1 sm:mt-2 text-lg sm:text-2xl font-bold text-slate-800">{data.transfer_count}</p>
        </div>

        {/* Flagged Transactions */}
        <div className="rounded-lg border border-slate-200 bg-white p-3 sm:p-4">
          <p className="text-xs sm:text-sm font-medium text-slate-600">Flagged</p>
          <p className="mt-1 sm:mt-2 text-lg sm:text-2xl font-bold text-yellow-600">{data.flagged_count}</p>
        </div>
      </div>

      {/* Income vs Expenses Chart */}
      {data.month_over_month.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-3 sm:p-4">
          <h3 className="mb-4 text-sm sm:text-base font-semibold text-slate-800">Income vs Expenses</h3>
          <div className="h-56 sm:h-80 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data.month_over_month}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="month" stroke="#64748b" style={{ fontSize: '12px' }} />
                <YAxis stroke="#64748b" style={{ fontSize: '12px' }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#ffffff',
                    border: '1px solid #e2e8f0',
                  }}
                  formatter={(value) => formatCurrency(Number(value))}
                />
                <Legend />
                <Bar dataKey="income" name="Income" fill="#16a34a" radius={[8, 8, 0, 0]} />
                <Bar dataKey="expenses" name="Expenses" fill="#dc2626" radius={[8, 8, 0, 0]} />
                <Line type="monotone" dataKey="net" name="Net" stroke="#2563eb" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Rolling 30-day spend Chart */}
      {data.rolling_30d_spend.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-3 sm:p-4">
          <h3 className="mb-1 text-sm sm:text-base font-semibold text-slate-800">Rolling 30-day spend</h3>
          <p className="mb-4 text-xs text-slate-500">
            total spent in the 30 days ending on each date — hover for the daily average
          </p>
          <div className="h-48 sm:h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.rolling_30d_spend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" stroke="#64748b" style={{ fontSize: '12px' }} />
                {/* Deliberately ONE y-axis. `daily_avg` is `amount / 30`, so plotting it
                    as a second series draws the identical curve at 1/30 scale against a
                    second scale — no added information, and a dual axis implies a
                    relationship between two quantities that are the same quantity. The
                    per-day figure lives in the tooltip instead. */}
                <YAxis stroke="#64748b" style={{ fontSize: '12px' }} />
                <Tooltip content={<RollingSpendTooltip />} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
