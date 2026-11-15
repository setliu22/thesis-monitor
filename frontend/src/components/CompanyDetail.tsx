import { useState } from 'react';
import { ArrowUpRight, Database, TrendingUp, FileText } from 'lucide-react';
import { date, format, labels } from '../api';
import type { Detail, Observation } from '../types';
export function Trend({ points }: { points: Observation[] }) {
  const valid = points.filter((p) => p.value !== null).slice(-8);
  if (valid.length < 2)
    return <div className="chart-empty">Sync at least two comparable periods to see a trend.</div>;
  const values = valid.map((p) => Number(p.value));
  const low = Math.min(...values) * 0.95,
    high = Math.max(...values) * 1.05;
  const range = high - low || 1;
  const coords = values.map((v, i) => [
    (i / (values.length - 1)) * 600,
    150 - ((v - low) / range) * 120,
  ]);
  const path = coords.map(([x, y], i) => (i ? 'L' : 'M') + x + ',' + y).join(' ');
  return (
    <div className="trend">
      <svg viewBox="-12 0 624 190" role="img" aria-label="Revenue trend by reporting period">
        <defs>
          <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#a6bd77" stopOpacity=".35" />
            <stop offset="100%" stopColor="#a6bd77" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[35, 90, 145].map((y) => (
          <line key={y} x1="0" x2="600" y1={y} y2={y} stroke="#e7ebe6" strokeDasharray="3 5" />
        ))}
        <path d={path + ' L600,170 L0,170 Z'} fill="url(#fill)" />
        <path d={path} fill="none" stroke="#456643" strokeWidth="2.5" />
        {coords.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="4" fill="#fff" stroke="#456643" strokeWidth="2">
            <title>
              {date(valid[i].end)}: {format(valid[i].value)}
            </title>
          </circle>
        ))}
      </svg>
      <div className="chart-labels">
        <span>{date(valid[0].end)}</span>
        <span>{date(valid[valid.length - 1].end)}</span>
      </div>
    </div>
  );
}
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
  const latest = (metric: string) => selected.filter((o) => o.metric === metric).at(-1);
  const cards = ['revenue', 'revenue_growth', 'operating_margin', 'free_cash_flow'];
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
              {detail.company.ticker} <span>·</span> SEC filing intelligence <span>·</span> USD
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
      <div className="metric-grid">
        {cards.map((key, i) => {
          const o = latest(key);
          return (
            <button
              className={'metric-card ' + (evidence === key ? 'focused' : '')}
              key={key}
              onClick={() => setEvidence(evidence === key ? null : key)}
            >
              <div className="metric-label">
                {labels[key]}
                <ArrowUpRight size={15} />
              </div>
              <strong>{format(o?.value, o?.unit)}</strong>
              <span>{o ? date(o.end) : 'Awaiting SEC data'}</span>
              {i === 1 && o?.value != null ? (
                <span className="metric-note">Year over year</span>
              ) : (
                <span className="metric-note">
                  {kind === 'quarter' ? 'Discrete quarter' : 'Full fiscal year'}
                </span>
              )}
            </button>
          );
        })}
      </div>
      {evidence && (
        <section className="panel evidence">
          <div className="section-heading">
            <h3>{labels[evidence]} · source evidence</h3>
            <button className="text-button" onClick={() => setEvidence(null)}>
              Close
            </button>
          </div>
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
                  <strong>{format(s.value)}</strong>
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
      {!end ? (
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
            <span className="eyebrow">REAL FILINGS. YOUR THESIS.</span>
            <h2>Connect to the source.</h2>
            <p>
              Your watchlist is ready.{' '}
              {secConfigured
                ? 'Refresh SEC data to bring in financial history and the latest filings.'
                : 'Add your SEC contact identity to start tracking financial changes from public company filings.'}
            </p>
            <button className="button primary" onClick={settings}>
              View data setup <ArrowUpRight size={15} />
            </button>
          </div>
        </section>
      ) : (
        <section className="panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">FINANCIAL TRAJECTORY</span>
              <h2>Revenue, over time.</h2>
            </div>
            <span className="badge neutral">
              {kind === 'quarter' ? 'Quarterly' : 'Annual'} · USD
            </span>
          </div>
          <Trend points={selected.filter((o) => o.metric === 'revenue')} />
          <p className="fine-print">
            Hover a point for its value. Click a metric above to inspect its source facts.
          </p>
        </section>
      )}
    </>
  );
}
