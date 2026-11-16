import { useState } from 'react';
import { ArrowUpRight, Database, TrendingUp, FileText } from 'lucide-react';
import { date, format, labels, instantMetrics, statementGroups } from '../api';
import FinancialHistory from './FinancialHistory';
import type { Detail } from '../types';
import Trend from './Trend';
export { default as Trend } from './Trend';
export default function CompanyDetail({
  detail,
  kind,
  setKind,
  secConfigured,
  settings,
}: {
  detail: Detail;
  kind: string;
  setKind: (k: string) => void;
  secConfigured: boolean;
  settings: () => void;
}) {
  const [evidence, setEvidence] = useState<string | null>(null);
  const selected = detail.observations.filter((o) => o.kind === kind);
  const latest = (metric: string) =>
    (instantMetrics.has(metric)
      ? detail.observations.filter((o) => o.kind === 'instant')
      : selected
    )
      .filter((o) => o.metric === metric)
      .at(-1);
  const end = latest('revenue')?.end;
  return (
    <>
      <div className="company-banner">
        <div className="company-identity">
          <div className="ticker-mark">{detail.company.ticker.slice(0, 4)}</div>
          <div>
            <div className="line">
              <h2>{detail.company.name}</h2>
              <span className="badge neutral">US EQUITY</span>
            </div>
            <p>
              {detail.company.ticker} <span>·</span> SEC filings <span>·</span> USD
            </p>
          </div>
        </div>
        <div className="segmented">
          <button
            className={kind === 'quarter' ? 'selected' : ''}
            onClick={() => setKind('quarter')}
          >
            Quarterly
          </button>
          <button className={kind === 'annual' ? 'selected' : ''} onClick={() => setKind('annual')}>
            Annual
          </button>
        </div>
      </div>
      {end && (
        <div className="data-summary">
          <span>
            {
              new Set(detail.observations.filter((o) => o.kind === 'quarter').map((o) => o.end))
                .size
            }{' '}
            quarters
          </span>
          <span>
            {new Set(detail.observations.filter((o) => o.kind === 'annual').map((o) => o.end)).size}{' '}
            fiscal years
          </span>
          <span>{detail.filings.length} recent filings</span>
          <a href="#financial-history" className="text-button">
            View financial history ↓
          </a>
        </div>
      )}
      {statementGroups.map((group) => (
        <section className="statement-metrics" key={group.title} aria-label={group.title}>
          <h3>{group.title}</h3>
          <div className="metric-grid">
            {group.metrics.map((key) => {
              const o = latest(key);
              return (
                <button
                  className={'metric-card ' + (evidence === key ? 'focused' : '')}
                  key={key}
                  onClick={() => {
                    const opening = evidence !== key;
                    setEvidence(opening ? key : null);
                    if (opening)
                      window.setTimeout(
                        () =>
                          document
                            .getElementById('selected-metric-history')
                            ?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
                        0,
                      );
                  }}
                >
                  <div className="metric-label">
                    {labels[key]}
                    <ArrowUpRight size={15} />
                  </div>
                  <strong>{format(o?.value, o?.unit)}</strong>
                  <Trend
                    compact
                    count={8}
                    metric={key}
                    points={detail.observations.filter(
                      (p) =>
                        p.metric === key && p.kind === (instantMetrics.has(key) ? 'instant' : kind),
                    )}
                  />

                  <span>{o ? date(o.end) : 'Metric unavailable'}</span>
                  {key.endsWith('_growth') && o?.value != null ? (
                    <span className="metric-note">Year over year</span>
                  ) : (
                    <span className="metric-note">
                      {instantMetrics.has(key)
                        ? 'Balance at reporting date'
                        : kind === 'quarter'
                          ? 'Discrete quarter'
                          : 'Full fiscal year'}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </section>
      ))}
      {evidence && (
        <section className="panel evidence" id="selected-metric-history">
          <div className="section-heading">
            <h3>{labels[evidence]} · source evidence</h3>
            <button className="text-button" onClick={() => setEvidence(null)}>
              Close
            </button>
          </div>
          <Trend
            metric={evidence}
            count={1000}
            points={detail.observations.filter(
              (p) =>
                p.metric === evidence &&
                p.kind === (instantMetrics.has(evidence) ? 'instant' : kind),
            )}
          />
          {latest(evidence) ? (
            <>
              <p>
                {latest(evidence)?.unavailable_reason ||
                  `${latest(evidence)?.derivation.replaceAll('_', ' ')} · Period ${date(latest(evidence)?.start)} – ${date(latest(evidence)?.end)}`}
              </p>
              {latest(evidence)?.sources.map((s, i) => (
                <div className="source-row" key={i}>
                  <div>
                    <code>{s.tag}</code>
                    <p>
                      {date(s.start)} – {date(s.end)} · Filed {date(s.filed)}
                    </p>
                  </div>
                  <strong>
                    {format(s.value, evidence === 'diluted_eps' ? 'USD/share' : 'USD')}
                  </strong>
                  {s.url && (
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noreferrer"
                      aria-label="Open source filing"
                    >
                      <ArrowUpRight size={17} />
                    </a>
                  )}
                </div>
              ))}
            </>
          ) : (
            <p className="muted">
              This metric is unavailable until a compatible SEC fact is synced.
            </p>
          )}
        </section>
      )}
      {!end && (
        <section className="connect-panel">
          <div className="connect-art">
            <div className="orbit one" />
            <div className="orbit two" />
            <span>
              <Database size={28} />
            </span>
            <i className="satellite">
              <FileText size={15} />
            </i>
            <i className="satellite second">
              <TrendingUp size={15} />
            </i>
          </div>
          <div>
            <span className="eyebrow">SEC DATA</span>
            <h2>No SEC data yet</h2>
            <p>
              {' '}
              {secConfigured
                ? 'Refresh SEC data to bring in financial history and the latest filings.'
                : 'Add your SEC contact identity to start tracking financial changes from public company filings.'}
            </p>
            <button className="button primary" onClick={settings}>
              View data setup <ArrowUpRight size={15} />
            </button>
          </div>
        </section>
      )}
      <FinancialHistory observations={detail.observations} kind={kind} />
    </>
  );
}
