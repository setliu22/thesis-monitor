import { Bell, Check, ArrowUpRight } from 'lucide-react';
import type { Alert } from '../types';
import { date, format, labels, operators } from '../api';
export default function AlertFeed({
  alerts,
  acknowledge,
  busy,
}: {
  alerts: Alert[];
  acknowledge: (id: number) => void;
  busy: boolean;
}) {
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <span className="eyebrow">
            SIGNALS / {alerts.filter((a) => !a.acknowledged_at).length} UNREAD
          </span>
          <h2>What needs your attention.</h2>
        </div>
        <Bell size={20} />
      </div>
      {alerts.length === 0 ? (
        <div className="inline-empty">
          <span className="empty-icon">
            <Check size={21} />
          </span>
          <p>No threshold alerts.</p>
          <span>Saved rules will flag changes in your latest reporting period.</span>
        </div>
      ) : (
        alerts.map((a) => (
          <article className={'alert-card ' + (a.acknowledged_at ? 'read' : '')} key={a.id}>
            <div className="section-heading">
              <span className="badge amber">
                {a.acknowledged_at ? 'Reviewed' : 'Review signal'}
              </span>
              <time>{date(a.created_at)}</time>
            </div>
            <h3>{a.evidence.rule_name || a.title}</h3>
            <p>
              {labels[a.evidence.metric]} is{' '}
              <strong>{format(a.evidence.value, a.evidence.unit)}</strong>,{' '}
              {operators[a.evidence.operator]} your {format(a.evidence.threshold, a.evidence.unit)}{' '}
              threshold.
            </p>
            <p className="muted">
              Period ended {date(a.evidence.end)} · Rule v{a.evidence.rule_version}
            </p>
            <details>
              <summary>Inspect evidence</summary>
              <pre>{JSON.stringify(a.evidence, null, 2)}</pre>
            </details>
            <div className="alert-actions">
              {a.evidence.sources?.[0]?.url && (
                <a
                  className="text-button"
                  href={a.evidence.sources[0].url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Source filing <ArrowUpRight size={14} />
                </a>
              )}
              <button
                className="text-button"
                disabled={busy || !!a.acknowledged_at}
                onClick={() => acknowledge(a.id)}
              >
                <Check size={15} />
                {a.acknowledged_at ? 'Acknowledged' : 'Mark reviewed'}
              </button>
            </div>
          </article>
        ))
      )}
    </section>
  );
}
