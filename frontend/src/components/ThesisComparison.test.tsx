import { render, screen, fireEvent } from '@testing-library/react';
import { test, expect, vi } from 'vitest';
import ThesisComparison, { financialChanges, narrativeHighlights } from './ThesisComparison';
import type { Detail, Observation } from '../types';
const observation = (metric: string, value: string, end: string): Observation => ({
  identity: metric + end,
  metric,
  value,
  end,
  start: end.startsWith('2026') ? '2026-07-01' : '2025-07-01',
  kind: 'quarter',
  unit: 'USD',
  sources: [
    { tag: metric, value, accn: 'test', filed: end, url: 'https://www.sec.gov/source', end },
  ],
  derivation: 'reported',
  unavailable_reason: null,
});
const detail = {
  company: { id: 1, ticker: 'TEST' },
  thesis: { id: 2, body: 'My thesis', version: 1 },
  filings: [
    {
      id: 1,
      form: '10-Q',
      report_date: '2026-09-30',
      filed: '2026-10-22',
      url: 'https://www.sec.gov/source',
    },
  ],
  observations: [
    observation('operating_cash_flow', '161314000', '2026-09-30'),
    observation('operating_cash_flow', '171065000', '2025-09-30'),
  ],
  analyses: [
    {
      id: 1,
      filing_id: 1,
      thesis_id: 2,
      model: 'model',
      result: {
        scope: 'Selected excerpts',
        review_status: 'needs_review',
        review_notes: ['Incorrect cash flow direction.'],
        rejected_count: 0,
        observations: [
          {
            summary: 'Operating cash flow increased',
            quote: 'Net cash provided 161,314 171,065',
            assessment: 'supports',
          },
        ],
      },
    },
  ],
} as Detail;
test('default summary uses calculated direction and hides unverified model notes', () => {
  render(<ThesisComparison detail={detail} busy={false} onAnalyze={() => {}} />);
  expect(screen.getByRole('heading', { name: 'Thesis comparison' })).toBeVisible();
  expect(screen.getByText(/Operating cash flow decreased 5.7%/)).toBeVisible();
  expect(screen.getByText('Operating cash flow increased')).not.toBeVisible();
  expect(screen.getByText('Net cash provided 161,314 171,065')).not.toBeVisible();
  fireEvent.click(screen.getByText('Full model notes and source evidence'));
  expect(screen.getByText('Operating cash flow increased')).toBeVisible();
  expect(screen.getByText('Incorrect cash flow direction.')).toBeVisible();
});
test('missing or incompatible comparison periods do not create a trend', () => {
  expect(
    financialChanges({ ...detail, observations: detail.observations.slice(0, 1) }, 1),
  ).toHaveLength(0);
  expect(financialChanges(detail, 99)).toHaveLength(0);
});
test('analysis action uses latest filing and marks stale thesis', () => {
  const analyze = vi.fn();
  render(
    <ThesisComparison
      detail={{ ...detail, thesis: { id: 3, version: 2, body: 'Edited' } }}
      busy={false}
      onAnalyze={analyze}
    />,
  );
  expect(screen.getByRole('heading', { name: 'Thesis comparison' })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Compare latest earnings' }));
  expect(analyze).toHaveBeenCalledWith(1);
});

test('margin changes remain valid when prior margin is negative or zero', () => {
  const current = { ...observation('operating_margin', '2', '2026-09-30'), unit: '%' };
  const previous = { ...observation('operating_margin', '-5', '2025-09-30'), unit: '%' };
  expect(financialChanges({ ...detail, observations: [current, previous] }, 1)[0].text).toContain(
    'increased 7.0 percentage points',
  );
  expect(
    financialChanges({ ...detail, observations: [current, { ...previous, value: '0' }] }, 1)[0]
      .text,
  ).toContain('increased 2.0 percentage points');
});

test('new comparisons show exact narrative evidence and collapse numeric detail', () => {
  const note = {
    summary: 'Relevant filing passage.',
    quote: 'The company develops optical communications for satellite constellations.',
    thesis_quote: 'Satellite communications are central to my thesis.',
    assessment: 'related',
  };
  render(
    <ThesisComparison
      detail={{
        ...detail,
        analyses: [
          {
            ...detail.analyses[0],
            result: {
              ...detail.analyses[0].result,
              selection_method: 'complete_passage_classification',
              observations: [note],
            },
          },
        ],
      }}
      busy={false}
      onAnalyze={() => {}}
    />,
  );
  expect(screen.getByRole('heading', { name: 'From the filing' })).toBeVisible();
  expect(
    screen
      .getAllByText(note.quote)
      .some((e) => e.closest('.narrative-highlights') && !e.closest('details')),
  ).toBe(true);
  expect(screen.getByText(/Operating cash flow decreased 5.7%/)).not.toBeVisible();
  fireEvent.click(screen.getByText('Calculated financial changes'));
  expect(screen.getByText(/Operating cash flow decreased 5.7%/)).toBeVisible();
});

test('narrative highlights favor specific thesis content over company history', () => {
  const history = {
    summary: '',
    quote: 'The company was founded in 1962 and has a long business history.',
    thesis_quote: 'Technology demand matters.',
    assessment: 'related',
  };
  const specific = {
    ...history,
    quote: 'Optical satellite communications and space sensors are deployed for secure networking.',
  };
  expect(
    narrativeHighlights(
      [history, specific],
      'Optical satellite communications, space sensors and secure networking are central to my thesis.',
    )[0],
  ).toBe(specific);
});

test('call passages retain speakers and are separate from the filing', () => {
  const comparison = structuredClone(detail);
  comparison.analyses[0].result.transcript = {
    status: 'included',
    quarter: '2026Q3',
    observations: [
      {
        summary: 'Related passage',
        quote: 'Space sensor demand is increasing.',
        thesis_quote: 'My thesis',
        assessment: 'related',
        speaker: 'Chief executive',
      },
    ],
  };
  render(<ThesisComparison detail={comparison} busy={false} onAnalyze={() => {}} />);
  expect(screen.getByRole('heading', { name: 'From the earnings call · 2026Q3' })).toBeVisible();
  expect(screen.getAllByText('Chief executive')[0]).toBeVisible();
  expect(screen.getAllByText('Space sensor demand is increasing.')[0]).toBeVisible();
});

test('missing call stays explicit while filing comparison remains available', () => {
  const comparison = structuredClone(detail);
  comparison.analyses[0].result.transcript = {
    status: 'unavailable',
    quarter: '2027Q1',
    reason: 'Transcript has not been published yet.',
  };
  render(<ThesisComparison detail={comparison} busy={false} onAnalyze={() => {}} />);
  expect(screen.getByText('Transcript has not been published yet.')).toBeVisible();
  expect(screen.getByText(/Operating cash flow decreased 5.7%/)).toBeVisible();
});

test('queued call review displays saved batch progress and quota wait', () => {
  const comparison = structuredClone(detail);
  comparison.jobs = [
    {
      id: 9,
      kind: 'analysis',
      status: 'queued',
      attempts: 0,
      error: 'Waiting for Groq free-tier allowance. Completed batches are saved.',
      created_at: '2026-11-18',
      finished_at: null,
      payload: { progress: { phase: 'transcript', completed_batches: 3, total_batches: 9 } },
    },
  ];
  render(<ThesisComparison detail={comparison} busy={true} onAnalyze={() => {}} />);
  expect(screen.getByRole('status')).toHaveTextContent('Call batches 3 of 9');
  expect(screen.getByRole('status')).toHaveTextContent('Completed batches are saved');
  expect(screen.getByRole('button', { name: 'Compare latest earnings' })).toBeDisabled();
});
