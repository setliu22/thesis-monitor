import { render, screen, fireEvent } from '@testing-library/react';
import { test, expect, vi } from 'vitest';
import ThesisComparison, { financialChanges } from './ThesisComparison';
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
  expect(screen.getByRole('heading', { name: 'Analysis needs review' })).toBeVisible();
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
  expect(screen.getByRole('heading', { name: 'Comparison uses an older thesis' })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Compare latest filing' }));
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
