import { useState } from 'react';
import { ArrowUpRight, X } from 'lucide-react';
import { date, format, labels, statementGroups } from '../api';
import Trend from './Trend';
import type { Observation } from '../types';

export default function FinancialHistory({
  observations,
  kind,
}: {
  observations: Observation[];
  kind: string;
}) {
  const [count, setCount] = useState(8);
  const [inspected, setInspected] = useState<Observation | null>(null);
  const flow = observations.filter((o) => o.kind === kind);
  const balances = observations.filter((o) => o.kind === 'instant');
  const allPeriods = [...new Set(flow.map((o) => o.end))].sort().reverse();
  const periods = allPeriods.slice(0, count);
  const balancePeriods = [...new Set(balances.map((o) => o.end))].sort().reverse().slice(0, count);
  const renderTable = (rows: string[], ends: string[], values: Observation[], name: string) => (
    <div className="table-wrap financial-table-wrap">
      <table aria-label={name} className="financial-table">
        <thead>
          <tr>
            <th scope="col">Metric</th>
            {ends.map((end) => (
              <th scope="col" key={end}>
                {date(end)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((metric) => (
            <tr key={metric}>
              <th scope="row">
                {labels[metric]}
                <Trend
                  compact
                  metric={metric}
                  points={values.filter((o) => o.metric === metric)}
                  count={count}
                />
              </th>
              {ends.map((end) => {
                const o = values.find((o) => o.metric === metric && o.end === end);
                return (
                  <td key={end}>
                    {o ? (
                      <button
                        className={'financial-value ' + (o.value === null ? 'unavailable' : '')}
                        onClick={() => setInspected(o)}
                        title={o.unavailable_reason || 'View values and source filings'}
                      >
                        {format(o.value, o.unit)}
                        {o.derivation === 'ytd_difference' && (
                          <sup aria-label="Derived quarter">*</sup>
                        )}
                      </button>
                    ) : (
                      <span className="unavailable">—</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  return (
    <section className="panel" id="financial-history">
      <div className="section-heading">
        <div>
          <span className="eyebrow">FINANCIAL STATEMENTS</span>
          <h2>Financial history</h2>
        </div>
        <label className="history-count">
          Show
          <select
            aria-label="Number of reporting periods"
            value={count}
            onChange={(e) => setCount(Number(e.target.value))}
          >
            <option value={8}>8 periods</option>
            <option value={16}>16 periods</option>
            <option value={1000}>All periods</option>
          </select>
        </label>
      </div>
      <p className="muted">
        {kind === 'quarter' ? 'Standalone quarters' : 'Full fiscal years'}. Values in USD; EPS in
        USD per share. Select a value to inspect its sources.
      </p>
      {statementGroups.map((group) => {
        const isBalance = group.title === 'Balance sheet';
        const ends = isBalance ? balancePeriods : periods;
        return (
          <section className="statement-history" key={group.title} aria-label={group.title}>
            <h3 className="balance-heading">{group.title}</h3>
            {isBalance && (
              <p className="muted">
                Balances at each reporting date, independent of the quarterly or annual setting.
              </p>
            )}
            {ends.length ? (
              renderTable(
                group.metrics,
                ends,
                isBalance ? balances : flow,
                `${group.title} history`,
              )
            ) : (
              <div className="inline-empty">
                <p>No financial history loaded.</p>
              </div>
            )}
          </section>
        );
      })}
      <p className="fine-print">
        * Calculated from compatible year-to-date figures. Free cash flow is operating cash flow
        minus capital expenditures. A dash means the metric is unavailable. Scroll horizontally for
        earlier periods.
      </p>
      {inspected && (
        <div className="history-evidence" role="region" aria-label="Selected financial sources">
          <div className="section-heading">
            <h3>
              {labels[inspected.metric]} · {date(inspected.end)}
            </h3>
            <button
              className="icon-button"
              onClick={() => setInspected(null)}
              aria-label="Close financial sources"
            >
              <X size={17} />
            </button>
          </div>
          <p>
            {format(inspected.value, inspected.unit)} · {inspected.derivation.replaceAll('_', ' ')}
          </p>
          <Trend
            metric={inspected.metric}
            count={1000}
            points={observations.filter(
              (o) => o.metric === inspected.metric && o.kind === inspected.kind,
            )}
          />
          {inspected.unavailable_reason && <p className="muted">{inspected.unavailable_reason}</p>}
          {inspected.sources.map((s, i) => (
            <div className="source-row" key={i}>
              <div>
                <code>{s.tag}</code>
                <p>
                  {s.start ? date(s.start) + ' – ' : ''}
                  {date(s.end)} · Filed {date(s.filed)}
                </p>
                {s.mapping_note && <p>{s.mapping_note}</p>}
              </div>
              <strong>
                {format(s.value, inspected.metric === 'diluted_eps' ? 'USD/share' : 'USD')}
              </strong>
              {s.url && (
                <a href={s.url} target="_blank" rel="noreferrer" className="text-button">
                  Filing <ArrowUpRight size={14} />
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
