export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch('/api' + path, {
      method,
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch {
    throw new Error(
      'Cannot connect to Thesis Monitor. Open the Thesis Monitor app to start local services, then reload this page.',
    );
  }
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(
      response.status >= 500
        ? 'The server is temporarily unavailable. Please try again shortly.'
        : 'The server returned an unexpected response. Please reload and try again.',
    );
  }
  if (!response.ok)
    throw new Error(
      typeof data.detail === 'string' ? data.detail : 'Please check your inputs and try again.',
    );
  return data as T;
}
export const labels: Record<string, string> = {
  revenue: 'Revenue',
  revenue_growth: 'Revenue growth',
  operating_income: 'Operating income',
  net_income: 'Net income',
  diluted_eps: 'Diluted EPS',
  cash: 'Cash & equivalents',
  assets: 'Total assets',
  liabilities: 'Total liabilities',
  equity: 'Equity',
  operating_margin: 'Operating margin',
  operating_cash_flow: 'Operating cash flow',
  cash_flow_growth: 'Cash flow growth',
  capital_expenditures: 'Capital expenditures',
  free_cash_flow: 'Free cash flow',
  debt: 'Long-term debt',
};
export const operators: Record<string, string> = {
  lt: 'below',
  lte: 'at or below',
  gt: 'above',
  gte: 'at or above',
};
export function format(value: string | null | undefined, unit = 'USD') {
  if (value == null) return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  if (unit === '%') return n.toFixed(1) + '%';
  if (unit === 'USD/share') return '$' + n.toFixed(2);
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(n);
}
export function date(value: string | null | undefined) {
  return value
    ? new Date(value.length === 10 ? value + 'T12:00:00Z' : value).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : 'Not synced yet';
}

export const instantMetrics = new Set(['debt', 'cash', 'assets', 'liabilities', 'equity']);
export const metricUnit = (metric: string) =>
  metric.includes('growth') || metric === 'operating_margin'
    ? '%'
    : metric === 'diluted_eps'
      ? 'USD/share'
      : 'USD';

export const statementGroups = [
  {
    title: 'Income statement',
    metrics: [
      'revenue',
      'revenue_growth',
      'operating_income',
      'operating_margin',
      'net_income',
      'diluted_eps',
    ],
  },
  { title: 'Balance sheet', metrics: ['cash', 'assets', 'liabilities', 'equity', 'debt'] },
  {
    title: 'Cash flow statement',
    metrics: ['operating_cash_flow', 'cash_flow_growth', 'capital_expenditures', 'free_cash_flow'],
  },
];
