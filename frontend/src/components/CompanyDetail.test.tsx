import { render, screen, fireEvent, within } from '@testing-library/react';
import { test, expect, vi } from 'vitest';
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
test('financial history groups statements and exposes metric source history', () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, json: async () => ({ mappings: [], attempts: [] }) })),
  );
  Element.prototype.scrollIntoView = vi.fn();
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
  const income = screen.getByRole('table', { name: 'Income statement history' });
  const cash = screen.getByRole('table', { name: 'Cash flow statement history' });
  expect(within(income).getByText('$120.00M')).toBeInTheDocument();
  expect(within(cash).getByText('$15.00M')).toBeInTheDocument();
  expect(within(cash).getByText('$3.00M')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /^Operating cash flow \$15/ }));
  expect(
    screen.getByRole('heading', { name: 'Operating cash flow · source evidence' }),
  ).toBeInTheDocument();
});
