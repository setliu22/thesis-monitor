import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import EventOutcome, { type Outcome } from './EventOutcome';

const outcome: Outcome = {
  status: 'reported',
  metrics: [
    {
      label: 'Monthly CPI inflation',
      value: '3.1',
      previous: '2.8',
      change: '0.3',
      unit: '%',
      direction: 'up',
      period: '2026-10-01',
      previous_period: '2026-09-01',
      why_it_matters: 'Prices are rising faster than in the prior monthly reading.',
    },
    {
      label: 'Producer-price inflation',
      value: '2.4',
      previous: '2.1',
      change: '0.3',
      unit: '%',
      direction: 'up',
      period: '2026-10-01',
      previous_period: '2026-09-01',
      why_it_matters: 'Producer prices can affect business input costs.',
    },
  ],
};

test('shows separate metric cards and explains the results with no stock selected', () => {
  const { container } = render(<EventOutcome outcome={outcome} />);
  const cards = container.querySelectorAll('.event-result-metric');
  expect(cards).toHaveLength(2);
  expect(screen.getByRole('heading', { name: 'What this could mean' })).toBeInTheDocument();
  expect(
    screen.getByText('Prices are rising faster than in the prior monthly reading.'),
  ).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: /What this could mean for/ })).not.toBeInTheDocument();
});
