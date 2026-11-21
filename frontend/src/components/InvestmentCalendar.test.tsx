import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import InvestmentCalendar from './InvestmentCalendar';

test('calendar context follows the selected stock and can be cleared', async () => {
  const fetchMock = vi.fn(async (url: string) => ({
    ok: true,
    json: async () =>
      url.includes('/calendar?')
        ? { events: [], missing_earnings: [], sources: [] }
        : {
            enabled: true,
            days: [7, 1],
            categories: ['earnings'],
            hour: 9,
            email_configured: false,
            timezone: 'America/New_York',
          },
  }));
  vi.stubGlobal('fetch', fetchMock);

  render(
    <InvestmentCalendar
      companies={[
        { id: 1, ticker: 'CACI', name: 'CACI International Inc' },
        { id: 2, ticker: 'MSFT', name: 'Microsoft Corporation' },
      ]}
      selectedCompanyId={1}
    />,
  );

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/context_company_id=1/), expect.anything()),
  );
  fireEvent.change(screen.getByRole('combobox', { name: 'Stock context' }), {
    target: { value: '' },
  });
  await waitFor(() =>
    expect(
      fetchMock.mock.calls.some(([url]) => url.includes('/calendar?') && !url.includes('context_company_id=')),
    ).toBe(true),
  );
});
