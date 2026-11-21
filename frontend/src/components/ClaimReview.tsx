import { useEffect, useRef, useState } from 'react';
import { api, date } from '../api';
import type { Detail } from '../types';

const labels: Record<string, string> = {
  waiting_for_thesis: 'Save your thesis to start a review.',
  configuration_required: 'Groq setup needed',
  waiting_for_filing: 'Waiting for an eligible filing',
  scheduled: 'Review scheduled',
  processing: 'Review in progress',
  quota_wait: 'Waiting for Groq allowance',
  provider_wait: 'Waiting to retry Groq',
  invalid_output_wait: 'Review response rejected. Retrying soon.',
  retry_wait: 'Review will retry',
  failed: 'Review needs attention',
  review_available: 'Ready to compare earnings with your thesis.',
};

function formatTime(value: string) {
  return new Date(value).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone: 'America/New_York',
    timeZoneName: 'short',
  });
}

export default function ClaimReview({
  detail,
  busy,
  onAnalyze,
  onSummaryQueued,
}: {
  detail: Detail;
  busy: boolean;
  onAnalyze: (id: number, rerun?: boolean, retryConnection?: boolean) => void;
  onSummaryQueued?: () => Promise<void>;
}) {
  const requested = useRef(new Set<number>());
  const [summaryErrorFor, setSummaryErrorFor] = useState<number>();
  const [summarySettledFor, setSummarySettledFor] = useState<number>();
  const filing = detail.filings
    .filter((f) => f.form === '10-Q' || f.form === '10-K')
    .sort((a, b) =>
      (b.report_date || b.filed).localeCompare(a.report_date || a.filed) ||
      b.filed.localeCompare(a.filed) || b.accession.localeCompare(a.accession),
    )[0];
  const current = filing?.id === detail.review?.filing_id ? detail.review : undefined;
  const analysis = detail.analyses.find(
    (a) =>
      a.filing_id === filing?.id && a.thesis_id === detail.thesis?.id && a.result.claim_assessments,
  );
  const job = detail.jobs.find(
    (j) =>
      j.kind === 'analysis' &&
      !j.payload?.summary_analysis_id &&
      (j.status === 'queued' || j.status === 'running') &&
      j.payload?.filing_id === filing?.id &&
      j.payload?.thesis_id === detail.thesis?.id,
  );
  const policy = analysis?.result.summary_policy;
  const summary =
    policy && analysis?.result.summary?.policy === policy ? analysis.result.summary : undefined;
  const summaryJob =
    policy && analysis
      ? detail.jobs.find(
          (j) =>
            j.payload?.summary_analysis_id === analysis.id && j.payload.summary_policy === policy,
        )
      : undefined;
  const canRequestSummary = Boolean(
    onSummaryQueued && analysis?.result.summary_eligible && !summary && !job && !summaryJob,
  );
  const analysisId = analysis?.id;
  const companyId = detail.company.id;

  useEffect(() => {
    if (!canRequestSummary || analysisId === undefined || requested.current.has(analysisId)) return;
    requested.current.add(analysisId);
    api<{ cached?: boolean }>(
      `/companies/${companyId}/analyses/${analysisId}/summary?automatic=true`,
      'POST',
    )
      .then(async (response) => {
        await onSummaryQueued?.();
        if (response.cached) setSummarySettledFor(analysisId);
      })
      .catch(() => setSummaryErrorFor(analysisId));
  }, [analysisId, canRequestSummary, companyId, onSummaryQueued]);

  const progress = job?.payload?.progress;
  const status = current?.status ?? (job ? 'processing' : 'review_available');
  const estimate = current?.completion_estimate;
  const next = current?.next_attempt ?? job?.available_at;
  const failed = status === 'failed';
  const canRetryConnection =
    status === 'provider_wait' &&
    job?.status === 'queued' &&
    job.payload?.wait_kind === 'groq_provider';
  const showReviewStatus = !analysis || Boolean(job) || failed;
  const summaryPending =
    summaryJob?.status === 'queued' ||
    summaryJob?.status === 'running' ||
    (canRequestSummary && summaryErrorFor !== analysisId && summarySettledFor !== analysisId);
  const paragraphs = summary?.sections.map((part) => part.text) ?? [];
  const summaryFailed =
    !summary &&
    (summaryJob?.status === 'failed' ||
      (analysisId !== undefined && summaryErrorFor === analysisId));
  if (!showReviewStatus && !summaryPending && !summaryFailed && !paragraphs.length) return null;

  return (
    <section className="panel thesis-comparison claim-review" aria-label="Thesis comparison">
      <header className="review-heading">
        <h2>Thesis comparison</h2>
        {filing && (
          <p className="review-meta">
            {filing.form} · {date(filing.report_date)}
            {analysis?.result.call?.status === 'included' && ' · Includes earnings call'}
          </p>
        )}
      </header>
      {paragraphs.length > 0 && (
        <div className="review-answer">
          {paragraphs.map((paragraph, index) => (
            <p key={index}>{paragraph}</p>
          ))}
        </div>
      )}
      {!summary && summaryPending && (
        <p role="status">{summaryJob?.error || 'Writing the comparison…'}</p>
      )}
      {summaryFailed && <p role="status">The comparison summary could not be written.</p>}
      {showReviewStatus && (
        <div role="status" className="review-status">
          <p>
            <strong>{labels[status] ?? 'Review in progress'}</strong>
          </p>
          {job && (
            <p>
              {estimate
                ? `Estimated ${estimate.scope} review finish · ${formatTime(estimate.at)}${status === 'provider_wait' ? ' if Groq reconnects on the next attempt' : ''}`
                : progress?.phase === 'thesis_claims'
                  ? 'Reading your thesis…'
                  : 'Estimating finish time…'}
            </p>
          )}
          {next && job?.status === 'queued' && new Date(next).getTime() > Date.now() && (
            <p>Next attempt · {formatTime(next)}</p>
          )}
          {(current?.last_error || current?.reason || job?.error) && (
            <p>{current?.last_error || current?.reason || job?.error}</p>
          )}
        </div>
      )}
      {showReviewStatus && filing && detail.thesis && (!job || canRetryConnection) && (
        <button
          className="text-button review-action"
          disabled={busy}
          onClick={() => onAnalyze(filing.id, failed, canRetryConnection)}
        >
          {canRetryConnection
            ? 'Retry Groq connection'
            : failed
              ? 'Retry review'
              : 'Review earnings'}
        </button>
      )}
    </section>
  );
}
