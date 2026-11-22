import ThesisPoints, { driverTitle, groupThesisPoints } from './ThesisPoints';
import ReviewAbout from './ReviewAbout';
import { date } from '../api';
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
  periodId,
  sharedPointNumbers,
}: {
  detail: Detail;
  periodId?: number;
  sharedPointNumbers?: ReadonlyMap<string, number>;
  busy: boolean;
  onAnalyze?: (id: number, rerun?: boolean, retryConnection?: boolean) => void;
}) {
  const filing = periodId === undefined ? detail.filings
    .filter((f) => f.form === '10-Q' || f.form === '10-K')
    .sort((a, b) =>
      (b.report_date || b.filed).localeCompare(a.report_date || a.filed) ||
      b.filed.localeCompare(a.filed) || b.accession.localeCompare(a.accession),
    )[0] : detail.filings.find((item) => item.id === periodId);
  const current = (detail.recent_reviews ?? [detail.review]).find((review) => review?.filing_id === filing?.id);
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
  const progress = job?.payload?.progress;
  const status = periodId !== undefined && !current?.review_id && current?.status === 'scheduled'
    ? 'review_available'
    : current?.status ?? (job ? 'processing' : 'review_available');
  const estimate = current?.completion_estimate;
  const next = current?.next_attempt ?? job?.available_at;
  const failed = status === 'failed';
  const canRetryConnection =
    status === 'provider_wait' &&
    job?.status === 'queued' &&
    job.payload?.wait_kind === 'groq_provider';
  const showReviewStatus = !analysis || Boolean(job) || failed;
  const points = analysis?.result.claims ?? [];
  const drivers = groupThesisPoints(points);
  const pointNumbers = sharedPointNumbers ??
    new Map([...drivers.keys()].map((driver, index) => [driver, index + 1]));
  const pointsById = new Map(points.map((point) => [
    point.id, { ...point, number: pointNumbers.get(driverTitle(point)) },
  ]));
  const displayParagraphs = (analysis?.result.claim_assessments ?? [])
    .filter((item) =>
      item.assessment !== 'insufficient evidence' &&
      item.citations.length > 0 && item.finding.trim(),
    )
    .map((item) => ({ claim_id: item.claim_id, text: item.finding }));

  return (
    <section className="panel thesis-comparison claim-review" aria-label="Thesis comparison">
      <header className="review-heading">
        {periodId === undefined && <h2>Thesis comparison</h2>}
        {filing && (
          <p className="review-meta">
            {filing.form} · {date(filing.report_date)}
            {analysis?.result.call?.status === 'included' && ' · Includes earnings call'}
          </p>
        )}
      </header>
      {periodId === undefined && <ReviewAbout />}
      {!sharedPointNumbers && points.length > 0 && (
        <div className="review-points">
          <h3>Thesis points</h3>
          <ThesisPoints drivers={drivers} />
        </div>
      )}
      {displayParagraphs.length > 0 && (
        <div className="review-answer">
          {displayParagraphs.map((paragraph, index) => {
            const point = pointsById.get(paragraph.claim_id);
            return (
              <p key={`${paragraph.claim_id}-${index}`}>
                {point && (
                  <><strong>{sharedPointNumbers ? `Point ${point.number}` : `${point.number}. ${point.text.replace(/[.!?]+$/, '')}`}:</strong>{' '}</>
                )}
                {paragraph.text}
              </p>
            );
          })}
        </div>
      )}
      {!showReviewStatus && !displayParagraphs.length && (
        <p role="status">Review complete. No direct findings to display.</p>
      )}
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
      {onAnalyze && periodId !== undefined && (status === 'complete' || (status === 'review_available' && analysis)) && !job && filing && detail.thesis && (
        <button className="text-button review-action" disabled={busy}
          onClick={() => onAnalyze(filing.id, true)}>
          Rerun review
        </button>
      )}
      {onAnalyze && showReviewStatus && filing && detail.thesis && (!job || canRetryConnection) && (periodId === undefined || failed || canRetryConnection) && (
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
