import { format } from '../api';
export type OutcomeMetric = {
  label: string;
  value: string;
  previous: string;
  change: string;
  unit: string;
  direction: 'up' | 'down' | 'unchanged';
  period: string;
  previous_period: string;
};
export type Outcome = {
  status: string;
  reason?: string;
  metrics?: OutcomeMetric[];
  context?: string;
  basis?: string;
  checked_at?: string;
  provisional?: boolean;
  sources?: { url: string; series?: string; vintage?: string }[];
  context_source?: string;
};
export type CompanyContext = {
  ticker: string;
  note: string;
  basis: string;
  facts: { metric: string; value: string; unit: string; period: string; source_urls: string[] }[];
  thesis_link?: string | null;
  thesis_basis?: string | null;
};
function value(v: string, unit: string) {
  if (unit === '%') return Number(v).toFixed(2) + '%';
  if (unit === 'jobs')
    return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(Number(v));
  return format(v, unit);
}
export function compactOutcome(outcome?: Outcome) {
  const metric = outcome?.status === 'reported' ? outcome.metrics?.[0] : null;
  return metric
    ? `${metric.direction === 'up' ? '↑' : metric.direction === 'down' ? '↓' : '→'} ${value(metric.value, metric.unit)}`
    : '';
}
export function outcomeTitle(outcome?: Outcome) {
  const m = outcome?.status === 'reported' ? outcome.metrics?.[0] : undefined;
  return m
    ? `${m.label}: ${value(m.value, m.unit)}; ${m.direction === 'up' ? 'higher than' : m.direction === 'down' ? 'lower than' : 'unchanged from'} previous ${value(m.previous, m.unit)}`
    : '';
}
function period(day: string, label = '') {
  if (label.startsWith('Fed target'))
    return new Date(day + 'T12:00:00Z').toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      timeZone: 'UTC',
    });
  if (label.startsWith('Real GDP'))
    return `Q${Math.floor(new Date(day + 'T12:00:00Z').getUTCMonth() / 3) + 1} ${day.slice(0, 4)}`;
  return new Date(day + 'T12:00:00Z').toLocaleDateString('en-US', {
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  });
}
export default function EventOutcome({
  outcome,
  companies = [],
}: {
  outcome?: Outcome;
  companies?: CompanyContext[];
}) {
  if (!outcome?.status) return <p className="fine-print">Result not loaded yet.</p>;
  if (outcome.status !== 'reported')
    return <p className="fine-print">{outcome.reason || 'Waiting for the reported result.'}</p>;
  return (
    <div className="event-outcome">
      <div className="event-result-metrics">
        {outcome.metrics?.map((m) => (
          <div className="event-result-metric" key={m.label}>
            <span>{m.label}</span>
            <strong>{value(m.value, m.unit)}</strong>
            <p>
              {m.direction === 'unchanged'
                ? 'Unchanged'
                : `${m.direction === 'up' ? 'Increased' : 'Decreased'} ${m.unit === '%' ? Math.abs(Number(m.change)).toFixed(2) + ' percentage points' : value(String(Math.abs(Number(m.change))), m.unit)}`}{' '}
              · Previous {value(m.previous, m.unit)}
            </p>
            <small>
              {period(m.period, m.label)} vs {period(m.previous_period, m.label)}
            </small>
          </div>
        ))}
      </div>
      {outcome.context && <p className="event-result-context">{outcome.context}</p>}
      {companies.length > 0 && (
        <div className="event-company-context">
          <h4>Your watchlist</h4>
          {companies.map((c) => (
            <article key={c.ticker}>
              <strong>{c.ticker}</strong>
              <p>{c.note}</p>
              <ul>
                {c.facts.map((f) => (
                  <li key={f.metric}>
                    {f.metric === 'debt'
                      ? 'Long-term debt'
                      : f.metric === 'cash'
                        ? 'Cash'
                        : 'Annual operating cash flow'}
                    : {format(f.value, f.unit)} <small>· {f.period}</small>
                  </li>
                ))}
              </ul>
              {c.thesis_link && (
                <details>
                  <summary>Link to your current thesis</summary>
                  <p>{c.thesis_link}</p>
                </details>
              )}
              <details>
                <summary>Financial sources</summary>
                <p className="fine-print">{c.basis}</p>
                {[...new Set(c.facts.flatMap((f) => f.source_urls))].map((url, i) => (
                  <a className="text-button" href={url} target="_blank" rel="noreferrer" key={url}>
                    SEC filing {i + 1} ↗
                  </a>
                ))}
              </details>
            </article>
          ))}
        </div>
      )}
      <details className="event-result-sources">
        <summary>Result sources and timing</summary>
        <p className="fine-print">{outcome.basis}</p>
        {outcome.provisional && (
          <p className="fine-print">
            Provisional snapshot; the release-date feed is still being refreshed.
          </p>
        )}
        {outcome.checked_at && (
          <p className="fine-print">Retrieved {new Date(outcome.checked_at).toLocaleString()}</p>
        )}
        {outcome.sources?.map((s, i) => (
          <a className="text-button" href={s.url} target="_blank" rel="noreferrer" key={s.url}>
            {s.series || `Report ${i + 1}`}
            {s.vintage ? ` · as of ${s.vintage}` : ''} ↗
          </a>
        ))}
        {outcome.context_source && (
          <a className="text-button" href={outcome.context_source} target="_blank" rel="noreferrer">
            How rates affect the economy ↗
          </a>
        )}
      </details>
    </div>
  );
}
