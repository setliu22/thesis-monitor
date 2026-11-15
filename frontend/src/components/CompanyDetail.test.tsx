import { render, screen, fireEvent, within } from '@testing-library/react';
import { test, expect } from 'vitest';
import CompanyDetail from './CompanyDetail';
import type { Detail, Observation } from '../types';

const observation = (metric: string, value: string, end: string): Observation => ({
  identity: metric + end,
  metric,
  value,
  unit: 'USD',
  start: end === '2025-06-30' ? '2025-04-01' : '2025-01-01',
  end,
  kind: 'quarter',
  derivation: 'reported',
  unavailable_reason: null,
  sources: [],
});
test('financial history exposes loaded metrics and chart selection', () => {
  const detail = {
    company: {
      id: 1,
      ticker: 'TEST',
      name: 'Synthetic Company',
      data_status: 'current',
      last_success: '2025-08-01',
    },
    observations: [
      observation('revenue', '100000000', '2025-03-31'),
      observation('revenue', '120000000', '2025-06-30'),
      observation('operating_cash_flow', '15000000', '2025-06-30'),
      observation('capital_expenditures', '3000000', '2025-06-30'),
    ],
    thesis: null,
    rules: [],
    filings: [],
    jobs: [],
    alerts: [],
    analyses: [],
  } as Detail;
  render(
    <CompanyDetail
      detail={detail}
      kind="quarter"
      setKind={() => {}}
      secConfigured
      settings={() => {}}
    />,
  );
  const table = screen.getByRole('table', { name: 'Financial history' });
  expect(within(table).getByText('$120.00M')).toBeInTheDocument();
  expect(within(table).getByText('$15.00M')).toBeInTheDocument();
  expect(within(table).getByText('$3.00M')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Chart metric'), {
    target: { value: 'operating_cash_flow' },
  });
  expect(screen.getByRole('heading', { name: 'Operating cash flow history' })).toBeInTheDocument();
});
