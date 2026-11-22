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
function backend(companyDetail: unknown = detail) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, options?: RequestInit) => {
      let value: unknown = url.endsWith('/metric-mappings')
        ? { mappings: [], attempts: [] }
        : url.startsWith('/api/calendar?')
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
                  : companyDetail;
      if (url.endsWith('/thesis') && options?.method === 'PUT')
        value = { version: 1, body: JSON.parse(String(options.body)).body };
      return { ok: true, json: async () => value };
    }),
  );
}
test('empty SEC data shows unavailable values and setup action', async () => {
  backend();
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Metrics & rules' }));
  expect(await screen.findByRole('heading', { name: 'Metrics & rules' })).toBeInTheDocument();
  expect(await screen.findByText('No SEC data yet')).toBeInTheDocument();
  expect(screen.queryByText('$8.63B')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /View data setup/i }));
  expect(screen.getByText(/SEC_USER_AGENT=/)).toBeInTheDocument();
});
test('metrics show the monitoring rules and the thesis tab shows the saved analysis', async () => {
  const summaryText = 'The filing says repeat orders increased 18%.';
  backend({
    ...detail,
    thesis: { id: 3, version: 1, body: 'Repeat orders should grow.' },
    review: { status: 'complete', filing_id: 4, thesis_id: 3 },
    filings: [{ id: 4, form: '10-Q', report_date: '2026-09-30', filed: '2026-10-22' }],
    analyses: [
      {
        id: 5,
        filing_id: 4,
        thesis_id: 3,
        result: {
          claim_assessments: [
            { claim_id: 'C1', assessment: 'supports', finding: summaryText, citations: ['E1'] },
          ],
        },
      },
    ],
  });
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Metrics & rules' }));
  await screen.findByText('No SEC data yet');
  expect(screen.getByRole('heading', { name: 'Monitoring rules' })).toBeVisible();
  expect(screen.queryByText(summaryText)).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Thesis' }));
  expect(screen.getByLabelText('Your investment thesis')).toBeVisible();
  expect(screen.getByText(summaryText)).toBeVisible();
  expect(screen.queryByRole('heading', { name: 'Monitoring rules' })).not.toBeInTheDocument();
});

test('thesis editor submits the written thesis', async () => {
  backend();
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Metrics & rules' }));
  await screen.findByText('No SEC data yet');
  fireEvent.click(screen.getByRole('button', { name: 'Thesis' }));
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

test('thesis history can be opened and one revision and its comparison are deleted', async () => {
  const initial = {
    ...detail,
    thesis: { id: 3, version: 3, body: 'Current thesis.' },
  };
  let revisions = [
    { id: 3, version: 3, body: 'Current thesis.', created_at: '2026-11-20' },
    { id: 2, version: 2, body: 'Earlier thesis.', created_at: '2026-11-19' },
  ];
  backend(initial);
  const original = fetch;
  const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
    if (url === '/api/companies/1/thesis/versions' && options?.method !== 'DELETE')
      return { ok: true, json: async () => revisions };
    if (url === '/api/companies/1/thesis/versions/2' && options?.method === 'DELETE') {
      revisions = revisions.filter((revision) => revision.id !== 2);
      return {
        ok: true,
        json: async () => ({ deleted_id: 2, current: initial.thesis }),
      };
    }
    return original(url, options);
  });
  vi.stubGlobal('fetch', fetchMock);
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Thesis' }));

  fireEvent.click(await screen.findByRole('button', { name: 'History' }));
  fireEvent.click(await screen.findByText(/Version 2/));
  expect(await screen.findByText('Earlier thesis.')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Delete version 2' }));

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/companies/1/thesis/versions/2',
      expect.objectContaining({ method: 'DELETE' }),
    ),
  );
  expect(confirm).toHaveBeenCalledWith(expect.stringContaining('comparison'));
  await waitFor(() => expect(screen.queryByText('Earlier thesis.')).not.toBeInTheDocument());
  confirm.mockRestore();
});

test('thesis history can be cleared and the editor becomes empty', async () => {
  const initial = {
    ...detail,
    thesis: { id: 2, version: 2, body: 'Saved thesis.' },
  };
  let cleared = false;
  backend(initial);
  const original = fetch;
  const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
    if (url === '/api/companies/1/thesis/versions' && options?.method !== 'DELETE')
      return {
        ok: true,
        json: async () => (cleared ? [] : [initial.thesis]),
      };
    if (url === '/api/companies/1/thesis/versions' && options?.method === 'DELETE') {
      cleared = true;
      return { ok: true, json: async () => ({ deleted: 1, current: null }) };
    }
    if (url === '/api/companies/1' && cleared)
      return { ok: true, json: async () => ({ ...initial, thesis: null }) };
    return original(url, options);
  });
  vi.stubGlobal('fetch', fetchMock);
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Thesis' }));
  fireEvent.click(await screen.findByRole('button', { name: 'History' }));
  expect(await screen.findByRole('textbox', { name: 'Your investment thesis' })).toHaveValue(
    'Saved thesis.',
  );
  fireEvent.click(screen.getByRole('button', { name: 'Delete all' }));

  expect(await screen.findByLabelText('Your investment thesis')).toHaveValue('');
  expect(confirm).toHaveBeenCalledWith(expect.stringContaining('comparison'));
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/companies/1/thesis/versions',
    expect.objectContaining({ method: 'DELETE' }),
  );
  confirm.mockRestore();
});

test('Review earnings queues a comparison for the latest filing', async () => {
  const initial = {
    ...detail,
    thesis: { id: 1, version: 1, body: 'Growth supports my thesis.' },
    review: { status: 'review_available', filing_id: 9, thesis_id: 1 },
    filings: [
      { id: 9, form: '10-Q', report_date: '2026-09-30', filed: '2026-10-22', accession: 'test' },
    ],
  };
  let queued = false;
  backend(initial);
  const original = fetch;
  const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
    if (url === '/api/settings')
      return {
        ok: true,
        json: async () => ({
          sec_configured: true,
          llm_configured: true,
          refresh_seconds: 3600,
          metrics: {},
        }),
      };
    if (url === '/api/companies/1/analyze' && options?.method === 'POST') {
      queued = true;
      return { ok: true, json: async () => ({ status: 'queued' }) };
    }
    if (url === '/api/companies/1' && queued)
      return {
        ok: true,
        json: async () => ({
          ...initial,
          review: { status: 'scheduled', filing_id: 9, thesis_id: 1 },
          jobs: [
            {
              id: 10,
              kind: 'analysis',
              status: 'queued',
              attempts: 0,
              error: null,
              created_at: '2026-11-20',
              finished_at: null,
              payload: { filing_id: 9, thesis_id: 1, review_id: 5 },
            },
          ],
        }),
      };
    return original(url, options);
  });
  vi.stubGlobal('fetch', fetchMock);
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Thesis' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Review earnings' }));

  await screen.findByText('Review scheduled');
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/companies/1/analyze',
    expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ filing_id: 9, rerun: false, retry_connection: false, recent_periods: true }),
    }),
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
  fireEvent.click(screen.getByRole('button', { name: 'Metrics & rules' }));
  await screen.findByText('No SEC data yet');
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
    fireEvent.click(screen.getByRole('button', { name: 'Metrics & rules' }));
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
          url.endsWith('/metric-mappings')
            ? { mappings: [], attempts: [] }
            : url === '/api/companies/1'
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
      await vi.advanceTimersByTimeAsync(60000);
    });
    expect(screen.getByText('Scheduled growth alert')).toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});

test('queued Groq analysis leaves SEC refresh available', async () => {
  backend();
  const original = fetch;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, options?: RequestInit) => {
      if (url === '/api/companies/1')
        return {
          ok: true,
          json: async () => ({
            ...detail,
            jobs: [
              {
                id: 10,
                kind: 'analysis',
                status: 'queued',
                attempts: 0,
                error: 'Waiting for Groq allowance.',
                created_at: '2026-11-18',
                finished_at: null,
              },
            ],
          }),
        };
      return original(url, options);
    }),
  );
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Metrics & rules' }));
  await screen.findByText('No SEC data yet');
  expect(screen.getByRole('button', { name: 'Refresh SEC data' })).toBeEnabled();
  expect(screen.queryByRole('button', { name: 'Sync in progress' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Thesis' }));
  expect(screen.getByRole('status')).toHaveTextContent('Comparison queued');
});

test('financial refresh does not block a Groq comparison of saved filings', async () => {
  backend();
  const original = fetch;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, options?: RequestInit) => {
      if (url === '/api/companies/1')
        return {
          ok: true,
          json: async () => ({
            ...detail,
            thesis: { id: 1, version: 1, body: 'Revenue growth supports my thesis.' },
            filings: [
              {
                id: 1,
                form: '10-Q',
                filed: '2026-10-22',
                report_date: '2026-09-30',
                accession: 'test',
                url: 'https://www.sec.gov/test',
              },
            ],
            jobs: [
              {
                id: 11,
                kind: 'refresh',
                status: 'queued',
                attempts: 0,
                error: null,
                created_at: '2026-11-18',
                finished_at: null,
              },
            ],
          }),
        };
      return original(url, options);
    }),
  );
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Metrics & rules' }));
  await screen.findByText('No SEC data yet');
  expect(screen.getByRole('button', { name: 'Sync in progress' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Thesis' }));
  expect(screen.getByRole('button', { name: 'Compare with latest earnings' })).toBeEnabled();
});

test('optional Groq mapping wait is not displayed as SEC syncing', async () => {
  backend();
  const original = fetch;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, options?: RequestInit) => {
      if (url === '/api/companies/1')
        return {
          ok: true,
          json: async () => ({
            ...detail,
            jobs: [
              {
                id: 12,
                kind: 'refresh',
                status: 'queued',
                attempts: 0,
                error: 'Waiting for Groq allowance.',
                created_at: '2026-11-18',
                finished_at: null,
                payload: { waiting_for: 'groq' },
              },
            ],
          }),
        };
      return original(url, options);
    }),
  );
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Metrics & rules' }));
  await screen.findByText('No SEC data yet');
  expect(screen.getByRole('button', { name: 'Refresh SEC data' })).toBeEnabled();
  expect(screen.queryByRole('button', { name: 'Sync in progress' })).not.toBeInTheDocument();
});

test('viewing a past thesis shows only its saved comparisons and preserves the current draft', async () => {
  const current = { id: 3, version: 3, body: 'Current thesis.', created_at: '2026-11-20' };
  const older = { id: 2, version: 2, body: 'Earlier thesis.', created_at: '2026-11-19' };
  backend({ ...detail, thesis: current });
  const original = fetch;
  const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
    if (url === '/api/companies/1/thesis/versions')
      return { ok: true, json: async () => [current, older] };
    if (url === '/api/companies/1/thesis/versions/2/comparisons')
      return { ok: true, json: async () => ({
        filings: [{ id: 9, form: '10-Q', report_date: '2026-09-30' }],
        analyses: [{ id: 1, filing_id: 9, thesis_id: 2, result: {
          claim_assessments: [{ claim_id: 'C1', assessment: 'supports',
            finding: 'Earlier saved finding.', citations: ['E1'] }],
        } }],
      }) };
    return original(url, options);
  });
  vi.stubGlobal('fetch', fetchMock);
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Thesis' }));
  fireEvent.change(await screen.findByLabelText('Your investment thesis'), { target: { value: 'Unsaved draft.' } });
  fireEvent.click(screen.getByRole('button', { name: 'History' }));
  fireEvent.click(await screen.findByRole('button', { name: 'View version 2' }));
  expect(await screen.findByText('Earlier saved finding.')).toBeVisible();
  expect(screen.getByText('Earlier thesis.')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Rerun review' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Back to current thesis' }));
  expect(screen.getByLabelText('Your investment thesis')).toHaveValue('Unsaved draft.');
  expect(screen.queryByText('Earlier saved finding.')).not.toBeInTheDocument();
});
