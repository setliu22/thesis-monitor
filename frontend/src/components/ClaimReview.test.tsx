import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { test, expect, vi, afterEach } from 'vitest';
import ClaimReview from './ClaimReview';
import type { Detail } from '../types';

afterEach(() => vi.unstubAllGlobals());

const policy = 'direct-evidence-v1';

const result = (finding: string) => ({
  scope: 'Selective filing review',
  summary_policy: policy,
  summary_eligible: true,
  summary: {
    policy,
    sections: [{ claim_id: 'C1', direction: 'challenges', text: finding, citations: ['E1'] }],
  },
  observations: [],
  rejected_count: 0,
  claims: [{ id: 'C1', text: 'Backlog converts faster this year.' }],
  claim_assessments: [
    {
      claim_id: 'C1',
      assessment: 'challenges' as const,
      finding,
      why_it_matters: '',
      uncertainty: '',
      citations: ['E1'],
    },
  ],
  evidence: [
    {
      id: 'E1',
      claim_id: 'C1',
      quote: 'Delivery moved into next year.',
      direction: 'challenges',
      source_type: 'filing',
      source_url: 'https://www.sec.gov/source',
      period: '2026-09-30',
    },
  ],
  coverage: { filing: { selective: true, selected_blocks: 2, total_blocks: 100 } },
  call: { status: 'pending' },
});
const detail = {
  company: { id: 1, ticker: 'TEST' },
  thesis: { id: 2, version: 2, body: 'Backlog converts faster this year.' },
  review: {
    status: 'filing_ready',
    filing_id: 1,
    thesis_id: 2,
    thesis_version: 2,
    call_status: { status: 'pending', reason: 'The matching call is not available yet.' },
  },
  filings: [
    { id: 1, form: '10-Q', report_date: '2026-09-30', filed: '2026-10-22' },
    { id: 2, form: '10-Q', report_date: '2026-06-30', filed: '2026-07-22' },
  ],
  jobs: [],
  analyses: [
    {
      id: 20,
      filing_id: 2,
      thesis_id: 2,
      created_at: '2026-11-18',
      result: result('Historical result finished later.'),
    },
    {
      id: 10,
      filing_id: 1,
      thesis_id: 2,
      created_at: '2026-11-17',
      result: result('Current report indicates delivery delays.'),
    },
  ],
  observations: [],
  rules: [],
  alerts: [],
} as unknown as Detail;

test('the latest filing stays selected when an older review finished later', () => {
  render(<ClaimReview detail={detail} busy={false} onAnalyze={vi.fn()} />);
  expect(screen.getByText('Current report indicates delivery delays.')).toBeVisible();
  expect(screen.queryByText('Historical result finished later.')).not.toBeInTheDocument();
});

test('changed thesis shows incomplete processing rather than a prior thesis verdict', () => {
  render(
    <ClaimReview
      detail={{
        ...detail,
        thesis: { id: 3, version: 3, body: 'New claim', created_at: '2026-11-20' },
        review: { ...detail.review!, thesis_id: 3, status: 'review_available' },
      }}
      busy={false}
      onAnalyze={vi.fn()}
    />,
  );
  expect(screen.getByRole('button', { name: 'Review earnings' })).toBeVisible();
  expect(screen.queryByText('Current report indicates delivery delays.')).not.toBeInTheDocument();
});

test('shows the finish estimate and allows a connection retry for the active review', () => {
  const onAnalyze = vi.fn();
  const next = '2099-01-05T18:10:00Z';
  render(
    <ClaimReview
      detail={{
        ...detail,
        analyses: [],
        review: {
          ...detail.review!,
          status: 'provider_wait',
          last_error: 'This process could not resolve Groq’s hostname.',
          next_attempt: next,
          completion_estimate: { at: '2099-01-05T18:30:00Z', scope: 'filing' },
        },
        jobs: [
          {
            id: 1,
            kind: 'analysis',
            status: 'queued',
            available_at: next,
            payload: {
              filing_id: 1,
              thesis_id: 2,
              wait_kind: 'groq_provider',
              last_attempt_at: '2099-01-05T18:05:00Z',
            },
          } as Detail['jobs'][number],
        ],
      }}
      busy={false}
      onAnalyze={onAnalyze}
    />,
  );
  const status = screen.getByRole('status');
  expect(status).toHaveTextContent('Estimated filing review finish · Jan 5, 1:30 PM EST');
  fireEvent.click(screen.getByRole('button', { name: 'Retry Groq connection' }));
  expect(onAnalyze).toHaveBeenCalledWith(1, false, true);
  expect(status).toHaveTextContent('Next attempt · Jan 5, 1:10 PM EST');
});

test('automatically requests the latest summary once and presents only the saved prose', async () => {
  const fetch = vi.fn(async () => ({ ok: true, json: async () => ({ id: 42 }) }));
  vi.stubGlobal('fetch', fetch);
  const onSummaryQueued = vi.fn(async () => {});
  const props = { busy: false, onAnalyze: vi.fn(), onSummaryQueued };
  const pending = structuredClone(detail);
  delete pending.analyses.find((analysis) => analysis.id === 10)!.result.summary;
  const { rerender, container } = render(<ClaimReview detail={pending} {...props} />);
  expect(screen.getByText('Writing the comparison…')).toBeVisible();
  await waitFor(() => expect(onSummaryQueued).toHaveBeenCalledOnce());
  expect(fetch).toHaveBeenCalledWith(
    '/api/companies/1/analyses/10/summary?automatic=true',
    expect.objectContaining({ method: 'POST' }),
  );
  rerender(<ClaimReview detail={structuredClone(pending)} {...props} />);
  expect(fetch).toHaveBeenCalledOnce();

  const complete = structuredClone(detail);
  const current = complete.analyses.find((analysis) => analysis.id === 10)!;
  current.result.summary = {
    policy,
    sections: [
      {
        claim_id: 'C1',
        direction: 'challenges',
        text: 'The filing pushes deliveries into next year.',
        citations: ['E1'],
      },
    ],
  };
  rerender(<ClaimReview detail={complete} {...props} />);
  expect(screen.getByText('The filing pushes deliveries into next year.')).toBeVisible();
  expect(screen.queryByText('Delivery timing')).not.toBeInTheDocument();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
  expect(container.querySelector('dialog, select, details')).toBeNull();
  expect(fetch).toHaveBeenCalledOnce();
});

test('a completed inconclusive review has no summary card or model request', () => {
  const copy = structuredClone(detail);
  const current = copy.analyses.find((analysis) => analysis.id === 10)!;
  current.result.summary_eligible = false;
  current.result.summary!.policy = 'old-policy';
  current.result.summary!.sections[0].text = 'The thesis is unsupported.';
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  render(<ClaimReview detail={copy} busy={false} onAnalyze={vi.fn()} onSummaryQueued={vi.fn()} />);
  expect(screen.queryByRole('region', { name: 'Thesis comparison' })).not.toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

test('a failed summary request leaves a visible status', async () => {
  const copy = structuredClone(detail);
  delete copy.analyses.find((analysis) => analysis.id === 10)!.result.summary;
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Unavailable')));
  render(<ClaimReview detail={copy} busy={false} onAnalyze={vi.fn()} onSummaryQueued={vi.fn()} />);
  expect(await screen.findByText('The comparison summary could not be written.')).toBeVisible();
});
