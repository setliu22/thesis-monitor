import { Bell, Check, ArrowUpRight } from 'lucide-react';
import type { Alert } from '../types';
import { date, format, labels, operators, api } from '../api';
import { useEffect, useState } from 'react';
type DeliveryStatus = {
  configured: boolean;
  recipient: string;
  deliveries: {
    id: number;
    alert_id: number;
    status: string;
    attempts: number;
    error: string | null;
  }[];
};
export default function AlertFeed({
  alerts,
  acknowledge,
  busy,
}: {
  alerts: Alert[];
  acknowledge: (id: number) => void;
  busy: boolean;
}) {
  const [delivery, setDelivery] = useState<DeliveryStatus | null>(null);
  useEffect(() => {
    let active = true;
    const load = () =>
      api<DeliveryStatus>('/notifications')
        .then((result) => {
          if (active && Array.isArray(result.deliveries)) setDelivery(result);
        })
        .catch(() => {});
    void load();
    const timer = window.setInterval(load, 15000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);
  return (
    <section className="panel" id="alerts">
      <div className="section-heading">
        <div>
          <span className="eyebrow">
            ALERTS / {alerts.filter((a) => !a.acknowledged_at).length} UNREAD
          </span>
          <h2>Alerts</h2>
        </div>
        <Bell size={20} />
      </div>
      <p className="muted">
        {delivery
          ? delivery.configured
            ? `Email alerts: ${delivery.recipient}. Delivery runs in a separate server process.`
            : 'Email alerts are off. The server needs a Resend API key and sender address.'
          : 'Email delivery status is unavailable.'}
      </p>
      {delivery?.deliveries
        .filter((d) => d.status === 'failed' || d.status === 'uncertain')
        .map((d) => (
          <p role="alert" key={d.id}>
            Email for alert #{d.alert_id}: {d.status}. {d.error}
          </p>
        ))}
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
              <span className="badge amber">{a.acknowledged_at ? 'Reviewed' : 'New alert'}</span>
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
            <p className="muted">
              Email: {delivery?.deliveries.find((d) => d.alert_id === a.id)?.status || 'not queued'}
              {delivery?.deliveries.find((d) => d.alert_id === a.id)?.status === 'accepted'
                ? ' by provider (inbox delivery not confirmed)'
                : ''}
            </p>
            <details>
              <summary>View calculation and sources</summary>
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
