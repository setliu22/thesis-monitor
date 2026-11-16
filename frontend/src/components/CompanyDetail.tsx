import { useState } from 'react';
import { ArrowUpRight, Database, TrendingUp, FileText } from 'lucide-react';
import { date, format, labels, instantMetrics } from '../api';
import FinancialHistory from './FinancialHistory';
import type { Detail, Observation } from '../types';
export function Trend({ points, metric = 'revenue' }: { points: Observation[]; metric?: string }) {
  const valid = points.filter((p) => p.value !== null).slice(-8);
  if (valid.length < 2)
    return <div className="chart-empty">Sync at least two comparable periods to see a trend.</div>;
  const values = valid.map((p) => Number(p.value));
  const low =
      Math.min(...values) -
      (Math.max(...values) - Math.min(...values) || Math.abs(values[0]) || 1) * 0.1,
    high =
      Math.max(...values) +
      (Math.max(...values) - Math.min(...values) || Math.abs(values[0]) || 1) * 0.1;
  const range = high - low || 1;
  const coords = values.map((v, i) => [
    (i / (values.length - 1)) * 600,
    150 - ((v - low) / range) * 120,
  ]);
  const path = coords.map(([x, y], i) => (i ? 'L' : 'M') + x + ',' + y).join(' ');
  return (
    <div className="trend">
      <svg
        viewBox="-12 0 624 190"
        role="img"
        aria-label={labels[metric] + ' trend by reporting period'}
      >
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
              {date(valid[i].end)}: {format(valid[i].value, valid[i].unit)}
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
  const [chartMetric, setChartMetric] = useState('revenue');
  const selected = detail.observations.filter((o) => o.kind === kind);
  const latest = (metric: string) =>
    (instantMetrics.has(metric)
      ? detail.observations.filter((o) => o.kind === 'instant')
      : selected
    )
      .filter((o) => o.metric === metric)
      .at(-1);
  const cards = [
    'revenue',
    'revenue_growth',
    'operating_margin',
    'net_income',
    'diluted_eps',
    'operating_cash_flow',
    'capital_expenditures',
    'free_cash_flow',
    'cash',
    'debt',
    'assets',
    'equity',
  ];
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
              <span>{o ? date(o.end) : 'Metric unavailable'}</span>
              {i === 1 && o?.value != null ? (
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
      ) : (
        <section className="panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">METRIC HISTORY</span>
              <h2>{labels[chartMetric]} history</h2>
            </div>
            <label className="chart-selector">
              Metric
              <select
                aria-label="Chart metric"
                value={chartMetric}
                onChange={(e) => setChartMetric(e.target.value)}
              >
                {Object.entries(labels)
                  .filter(([key]) => !instantMetrics.has(key))
                  .map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <Trend points={selected.filter((o) => o.metric === chartMetric)} metric={chartMetric} />
          <p className="fine-print">
            Hover a point for its value. Click a metric above to inspect its source facts.
          </p>
        </section>
      )}
      <FinancialHistory observations={detail.observations} kind={kind} />
    </>
  );
}
