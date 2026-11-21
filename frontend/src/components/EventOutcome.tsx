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
  why_it_matters?: string;
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
  headline?: string;
  relation: string;
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
  const explanations = outcome.metrics?.filter((metric) => metric.why_it_matters) ?? [];
  return (
    <div className="event-outcome">
      <div className="event-result-metrics">
        {outcome.metrics?.map((m) => (
          <article className="event-result-metric" key={m.label}>
            <span className="event-result-metric-eyebrow">Reported metric</span>
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
            {companies.length > 0 && m.why_it_matters && (
              <p className="event-metric-why">
                <b>Why it matters</b>
                {m.why_it_matters}
              </p>
            )}
          </article>
        ))}
      </div>
      {companies.length === 0 && explanations.length > 0 && (
        <section className="event-company-context">
          <h4>What this could mean</h4>
          {explanations.map((metric) => (
            <p key={metric.label}>
              {explanations.length > 1 && <strong>{metric.label}. </strong>}
              {metric.why_it_matters}
            </p>
          ))}
        </section>
      )}
      {companies.length > 0 && (
        <div className="event-company-context">
          <h4>What this could mean for {companies[0].ticker}</h4>
          {companies.map((c) => (
            <article key={c.ticker}>
              {c.headline && <strong>{c.headline}</strong>}
              <p className="event-stock-relation">{c.relation}</p>
              {c.facts.length > 0 && (
                <ul>
                  {c.facts.map((f) => (
                    <li key={f.metric}>
                      {f.metric === 'debt'
                        ? 'Long-term debt'
                        : f.metric === 'cash'
                          ? 'Cash'
                          : f.metric === 'operating_cash_flow'
                            ? 'Operating cash flow'
                            : f.metric === 'revenue_growth'
                              ? 'Revenue growth'
                              : 'Operating margin'}
                      : {format(f.value, f.unit)} <small>· {f.period}</small>
                    </li>
                  ))}
                </ul>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
