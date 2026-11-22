import { useEffect, useState } from 'react';
import { api } from '../api';
import type { Detail, ThesisVersion } from '../types';
import ThesisComparison from './ThesisComparison';

type SavedComparisons = Pick<Detail, 'analyses' | 'filings'>;

export default function ArchivedThesisComparison({
  detail,
  version,
}: {
  detail: Detail;
  version: ThesisVersion;
}) {
  const [saved, setSaved] = useState<SavedComparisons>();
  const [error, setError] = useState('');
  const companyId = detail.company.id;
  const versionId = version.id;
  useEffect(() => {
    let active = true;
    api<SavedComparisons>(`/companies/${companyId}/thesis/versions/${versionId}/comparisons`)
      .then((result) => { if (active) setSaved(result); })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : 'Could not load saved comparisons.');
      });
    return () => { active = false; };
  }, [companyId, versionId]);

  if (!saved?.analyses.length) return (
    <section className="panel">
      <h2>Thesis comparison</h2>
      {error ? <p role="alert">{error}</p> : (
        <p role="status">{saved ? 'No saved comparisons for this version.' : 'Loading saved comparisons…'}</p>
      )}
    </section>
  );

  const archived = { ...detail, ...saved, thesis: version, jobs: [], review: undefined };
  const modern = saved.analyses.filter((analysis) => analysis.result.claim_assessments);
  const legacy = saved.analyses.filter((analysis) => !analysis.result.claim_assessments);
  return (
    <>
      {modern.length > 0 && (
        <ThesisComparison busy={false} detail={{
          ...archived,
          analyses: modern,
          recent_reviews: modern.map((analysis) => ({
            status: 'complete', filing_id: analysis.filing_id, thesis_id: version.id,
          })),
        }} />
      )}
      {legacy.map((analysis) => (
        <ThesisComparison key={analysis.id} busy={false}
          detail={{ ...archived, analyses: [analysis], recent_reviews: [] }} />
      ))}
    </>
  );
}
