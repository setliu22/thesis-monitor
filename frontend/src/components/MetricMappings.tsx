import { useEffect, useState } from 'react';
import { api, labels } from '../api';

type Mapping = {
  id: string;
  source_url: string;
  structural_checks_passed?: boolean;
  metric: string;
  namespace: string;
  tag: string;
  status: string;
  quote: string;
  reason: string;
  validation: string;
  at: string;
  model: string;
};
type Registry = { mappings: Mapping[]; attempts: { metric: string; status: string; at: string }[] };
export default function MetricMappings({
  companyId,
  refreshed,
}: {
  companyId: number;
  refreshed: string | null;
}) {
  const [data, setData] = useState<Registry | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let live = true;
    setData(null);
    setError('');
    api<Registry>(`/companies/${companyId}/metric-mappings`)
      .then((d) => {
        if (live) setData(d);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [companyId, refreshed]);
  async function disable(id: string, approve = false) {
    setBusy(true);
    setError('');
    try {
      await api(
        `/companies/${companyId}/metric-mappings/${id}${approve ? '/approve' : ''}`,
        approve ? 'POST' : 'DELETE',
      );
      setData(await api<Registry>(`/companies/${companyId}/metric-mappings`));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!error && !data) return null;
  return (
    <details className="panel mapping-coverage">
      <summary>
        Metric mapping coverage
        {data
          ? ` · ${data.mappings.filter((m) => m.status === 'accepted').length} accepted · ${data.mappings.filter((m) => m.status === 'pending').length} need review`
          : ''}
      </summary>
      <p className="muted">
        Groq investigates missing metrics during financial refreshes. Only mappings that pass source
        and definition checks are applied, for this company only.
      </p>
      {data && !data.mappings.length && !data.attempts.length && (
        <p className="muted">No mapping investigation has been needed for this company yet.</p>
      )}
      {error && <p className="error-text">{error}</p>}
      {data?.mappings.map((m) => (
        <article className="history-evidence" key={m.id}>
          <div className="section-heading">
            <h3>
              {labels[m.metric] || m.metric} · {m.status}
            </h3>
            {m.status === 'pending' && m.structural_checks_passed && (
              <button disabled={busy} className="text-button" onClick={() => disable(m.id, true)}>
                Approve definition for this company
              </button>
            )}
            {m.status !== 'disabled' && (
              <button disabled={busy} className="text-button" onClick={() => disable(m.id)}>
                {m.status === 'accepted' ? 'Disable mapping' : 'Dismiss proposal'}
              </button>
            )}
          </div>
          <code>
            {m.namespace}:{m.tag}
          </code>
          <blockquote>{m.quote}</blockquote>
          {m.source_url && (
            <a className="text-button" href={m.source_url} target="_blank" rel="noreferrer">
              View source filing ↗
            </a>
          )}
          <p>{m.reason}</p>
          <p className="fine-print">
            {m.validation} · {m.model} · {new Date(m.at).toLocaleDateString()}
          </p>
        </article>
      ))}
      {data && data.attempts.length > 0 && (
        <p className="fine-print">
          Latest investigation: {new Date(data.attempts.at(-1)!.at).toLocaleDateString()} ·{' '}
          {data.attempts.at(-1)!.status}. A completed investigation may find no safe mapping.
          Unresolved metrics remain unavailable. Disabling queues a financial refresh; previous
          versions remain in the audit history.
        </p>
      )}
    </details>
  );
}
