import { useEffect, useState } from 'react';
import { api, date } from '../api';
import type { ThesisVersion } from '../types';

export default function ThesisHistory({
  companyId,
  currentThesisId,
  onDeleted,
}: {
  companyId: number;
  currentThesisId?: number;
  onDeleted: (current: ThesisVersion | null, deletedCurrent: boolean) => Promise<void>;
}) {
  const [versions, setVersions] = useState<ThesisVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState('');

  async function loadVersions() {
    setLoading(true);
    setError('');
    try {
      setVersions(await api<ThesisVersion[]>(`/companies/${companyId}/thesis/versions`));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load thesis history.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadVersions();
  }, [companyId]);

  async function deleteVersion(version: ThesisVersion) {
    const confirmed = window.confirm(
      `Delete thesis version ${version.version} and its saved comparison results? This cannot be undone.`,
    );
    if (!confirmed) return;
    setDeleting(true);
    setError('');
    try {
      const result = await api<{ deleted_id: number; current: ThesisVersion | null }>(
        `/companies/${companyId}/thesis/versions/${version.id}`,
        'DELETE',
      );
      await loadVersions();
      await onDeleted(result.current, result.deleted_id === currentThesisId);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not delete this thesis version.');
    } finally {
      setDeleting(false);
    }
  }

  async function deleteAll() {
    const confirmed = window.confirm(
      `Delete all ${versions.length} thesis versions and their saved comparison results? This cannot be undone.`,
    );
    if (!confirmed) return;
    setDeleting(true);
    setError('');
    try {
      await api<{ deleted: number; current: null }>(
        `/companies/${companyId}/thesis/versions`,
        'DELETE',
      );
      setVersions([]);
      await onDeleted(null, true);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not delete thesis history.');
    } finally {
      setDeleting(false);
    }
  }

  return (
    <section className="thesis-history" aria-label="Thesis history">
      <div className="section-heading">
        <h3>Saved versions</h3>
        {versions.length > 0 && (
          <button className="text-button danger" disabled={loading || deleting} onClick={deleteAll}>
            Delete all
          </button>
        )}
      </div>
      {error && <p role="alert">{error}</p>}
      {loading ? (
        <p role="status">Loading history…</p>
      ) : versions.length === 0 ? (
        <p>No saved versions.</p>
      ) : (
        <div className="thesis-version-list">
          {versions.map((version) => (
            <article className="thesis-version" key={version.id}>
              <details>
                <summary>
                  Version {version.version} · {date(version.created_at)}
                  {version.id === currentThesisId && <span> · Current</span>}
                </summary>
                <p>{version.body}</p>
              </details>
              <button
                className="text-button danger"
                aria-label={`Delete version ${version.version}`}
                disabled={loading || deleting}
                onClick={() => deleteVersion(version)}
              >
                Delete
              </button>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
