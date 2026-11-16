import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { test, expect, vi } from 'vitest';
import App from './App';

const company = {
  id: 1,
  ticker: 'CACI',
  name: 'CACI International Inc',
  data_status: 'empty',
  last_success: null,
};
const detail = {
  company,
  thesis: null,
  rules: [],
  observations: [],
  alerts: [],
  filings: [],
  jobs: [],
  analyses: [],
};
function backend() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, options?: RequestInit) => {
      let value: unknown = url.startsWith('/api/calendar?')
        ? { events: [], missing_earnings: [], sources: [] }
        : url === '/api/reminder-settings'
          ? {
              enabled: true,
              days: [7, 1],
              categories: ['earnings'],
              hour: 9,
              email_configured: true,
              timezone: 'America/New_York',
            }
          : url === '/api/notifications'
            ? { configured: false, recipient: '', deliveries: [] }
            : url === '/api/settings'
              ? {
                  sec_configured: false,
                  llm_configured: false,
                  refresh_seconds: 3600,
                  metrics: { revenue: 'USD' },
                }
              : url === '/api/companies'
                ? [company]
                : detail;
      if (url.endsWith('/thesis') && options?.method === 'PUT')
        value = { version: 1, body: JSON.parse(String(options.body)).body };
      return { ok: true, json: async () => value };
    }),
  );
}
test('empty SEC data shows unavailable values and setup action', async () => {
  backend();
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Overview' }));
  expect(await screen.findByRole('heading', { name: 'Watchlist overview' })).toBeInTheDocument();
  expect(await screen.findByText('No SEC data yet')).toBeInTheDocument();
  expect(screen.queryByText('$8.63B')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Data settings/i }));
  expect(screen.getByText(/SEC_USER_AGENT=/)).toBeInTheDocument();
});
test('thesis editor submits the written thesis', async () => {
  backend();
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Overview' }));
  await screen.findByText('No SEC data yet');
  fireEvent.click(screen.getByRole('button', { name: 'Thesis & rules' }));
  const input = screen.getByLabelText('Your investment thesis');
  fireEvent.change(input, { target: { value: 'Cash generation supports the thesis.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save thesis' }));
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      '/api/companies/1/thesis',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ body: 'Cash generation supports the thesis.' }),
      }),
    ),
  );
});

test('failed rule save keeps the editable form open', async () => {
  backend();
  const original = fetch;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, options?: RequestInit) =>
      url.endsWith('/rules') && options?.method === 'POST'
        ? { ok: false, json: async () => ({ detail: 'Database temporarily unavailable' }) }
        : original(url, options),
    ),
  );
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Overview' }));
  await screen.findByText('No SEC data yet');
  fireEvent.click(screen.getByRole('button', { name: 'Thesis & rules' }));
  fireEvent.click(screen.getByRole('button', { name: 'Add rule' }));
  fireEvent.change(screen.getByLabelText('Rule name'), { target: { value: 'Growth floor' } });
  fireEvent.change(screen.getByLabelText(/Threshold/), { target: { value: '5' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save rule' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Database temporarily unavailable');
  expect(screen.getByLabelText('Rule name')).toBeInTheDocument();
});

test('idle dashboard discovers new alerts on its background refresh', async () => {
  vi.useFakeTimers();
  try {
    backend();
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Overview' }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText('No SEC data yet')).toBeInTheDocument();
    const updated = {
      ...detail,
      alerts: [
        {
          id: 42,
          title: 'New signal',
          created_at: '2025-08-01',
          acknowledged_at: null,
          evidence: {
            metric: 'revenue_growth',
            value: '4',
            unit: '%',
            end: '2025-06-30',
            threshold: '5',
            operator: 'lt',
            rule_version: 1,
            rule_name: 'Scheduled growth alert',
            sources: [],
          },
        },
      ],
    };
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => ({
        ok: true,
        json: async () =>
          url === '/api/companies/1'
            ? updated
            : url === '/api/companies'
              ? [company]
              : {
                  sec_configured: false,
                  llm_configured: false,
                  refresh_seconds: 3600,
                  metrics: { revenue: 'USD' },
                },
      })),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000);
    });
    expect(screen.getByText('Scheduled growth alert')).toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});
