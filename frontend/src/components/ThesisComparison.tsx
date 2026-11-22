import ThesisPoints, { groupThesisPoints } from './ThesisPoints';
import ReviewAbout from './ReviewAbout';
import AnalysisQueue from './AnalysisQueue';
import ClaimReview from './ClaimReview';
import { date, format, labels } from '../api';
import type { Detail, Observation } from '../types';

function duration(o: Observation) {
  return o.start ? (Date.parse(o.end) - Date.parse(o.start)) / 86400000 : 0;
}
export function financialChanges(detail: Detail, filingId: number) {
  const filing = detail.filings.find((f) => f.id === filingId);
  if (!filing) return [];
  const kind = filing.form.startsWith('10-K') ? 'annual' : 'quarter';
  return ['revenue', 'operating_margin', 'operating_cash_flow'].flatMap((metric) => {
    const current = detail.observations.find(
      (o) =>
        o.metric === metric && o.kind === kind && o.end === filing.report_date && o.value !== null,
    );
    if (!current || !Number.isFinite(Number(current.value))) return [];
    const previous = detail.observations
      .filter(
        (o) =>
          o.metric === metric &&
          o.kind === kind &&
          o.value !== null &&
          (Date.parse(current.end) - Date.parse(o.end)) / 86400000 >= 350 &&
          (Date.parse(current.end) - Date.parse(o.end)) / 86400000 <= 380 &&
          Math.abs(duration(current) - duration(o)) <= 10 &&
          [...new Set(o.sources.map((s) => s.tag))].sort().join('|') ===
            [...new Set(current.sources.map((s) => s.tag))].sort().join('|'),
      )
      .sort((a, b) => b.end.localeCompare(a.end))[0];
    if (
      !previous ||
      !Number.isFinite(Number(previous.value)) ||
      (metric !== 'operating_margin' && Number(previous.value) <= 0)
    )
      return [];
    const delta = Number(current.value) - Number(previous.value);
    const change = metric === 'operating_margin' ? delta : (delta / Number(previous.value)) * 100;
    const direction = delta > 0 ? 'increased' : delta < 0 ? 'decreased' : 'was unchanged';
    return [
      {
        metric,
        current,
        previous,
        text: `${labels[metric]} ${direction}${delta === 0 ? '' : ` ${Math.abs(change).toFixed(1)}${metric === 'operating_margin' ? ' percentage points' : '%'}`} year over year, from ${format(previous.value, previous.unit)} to ${format(current.value, current.unit)}.`,
      },
    ];
  });
}

export function narrativeHighlights(
  observations: Detail['analyses'][number]['result']['observations'],
  thesis: string,
) {
  const stop = new Set(
    'this that with from their which have been into company business stock because thesis could would should these those about through'.split(
      ' ',
    ),
  );
  const words = (text: string) =>
    new Set(
      (text.toLowerCase().match(/[a-z]{4,}/g) ?? [])
        .filter((w) => !stop.has(w))
        .map((w) => (w.endsWith('s') ? w.slice(0, -1) : w)),
    );
  const query = words(thesis);
  const unique = observations.filter(
    (o, i, rows) => rows.findIndex((x) => x.quote === o.quote) === i,
  );
  const vocab = unique.map((o) => words(o.quote));
  const scored = unique
    .map((note, i) => ({
      note,
      score:
        [...vocab[i]]
          .filter((w) => query.has(w))
          .reduce(
            (sum, w) =>
              sum + 1 + Math.log((unique.length + 1) / (vocab.filter((v) => v.has(w)).length + 1)),
            0,
          ) / Math.sqrt(1 + note.quote.split(/\s+/).length / 40),
    }))
    .sort((a, b) => b.score - a.score);
  const selected: typeof unique = [];
  for (const { note } of scored) {
    if (!selected.some((o) => o.thesis_quote === note.thesis_quote)) selected.push(note);
    if (selected.length === 3) return selected;
  }
  for (const { note } of scored) {
    if (!selected.includes(note)) selected.push(note);
    if (selected.length === 3) break;
  }
  return selected;
}

export default function ThesisComparison({
  detail,
  busy,
  onAnalyze,
}: {
  detail: Detail;
  busy: boolean;
  onAnalyze?: (filingId: number, rerun?: boolean, retryConnection?: boolean) => void;
}) {
  const periods = detail.recent_reviews ?? [];
  if (periods.length) {
    const latestId = periods[0].filing_id;
    const points = groupThesisPoints(periods.flatMap(({ filing_id }) => {
      const analysis = detail.analyses.find((item) =>
        item.filing_id === filing_id && item.thesis_id === detail.thesis?.id &&
        item.result.claim_assessments,
      );
      return analysis?.result.claims ?? [];
    }));
    const pointNumbers = new Map([...points.keys()].map((point, index) => [point, index + 1]));
    return (
      <div className="thesis-period-reviews">
        <div className="panel">
          <div className="section-heading">
            <h2>Thesis comparison</h2>
            {latestId != null && detail.thesis && onAnalyze && (
              <button className="button secondary" disabled={busy}
                onClick={() => onAnalyze(latestId)}>
                Review latest {periods.length === 1 ? 'earnings' : `${periods.length} earnings periods`}
              </button>
            )}
          </div>
          <ReviewAbout />
        </div>
        {points.size > 0 && (
          <section className="panel review-points" aria-label="Thesis points">
            <h3>Thesis points</h3>
            <ThesisPoints drivers={points} />
          </section>
        )}
        {periods.map(({ filing_id }) => filing_id != null && (
          <ClaimReview key={filing_id} periodId={filing_id} detail={detail} sharedPointNumbers={pointNumbers}
            busy={busy} onAnalyze={onAnalyze} />
        ))}
      </div>
    );
  }
  if (detail.review || detail.analyses.some((a) => a.result.claim_assessments))
    return (
      <ClaimReview
        detail={detail}
        busy={busy}
        onAnalyze={onAnalyze}
      />
    );
  const analysis = detail.analyses[0];
  const job = detail.jobs?.find(
    (j) => j.kind === 'analysis' && ['queued', 'running'].includes(j.status),
  );
  const progress = job?.payload?.progress;
  const latest = detail.filings
    .filter((f) => f.form === '10-K' || f.form === '10-Q')
    .sort((a, b) =>
      (b.report_date || b.filed).localeCompare(a.report_date || a.filed) ||
      b.filed.localeCompare(a.filed) || b.accession.localeCompare(a.accession),
    )[0];
  const filing = detail.filings.find((f) => f.id === analysis?.filing_id);
  const stale = Boolean(analysis && detail.thesis && analysis.thesis_id !== detail.thesis.id);
  const changes = analysis ? financialChanges(detail, analysis.filing_id) : [];
  const narrative =
    !stale && analysis?.result.selection_method === 'complete_passage_classification'
      ? narrativeHighlights(analysis.result.observations, detail.thesis?.body ?? '')
      : [];
  const financialContent = (
    <>
      {' '}
      {changes.length > 0 ? (
        <ul className="thesis-change-list">
          {changes.map((c) => (
            <li key={c.metric}>
              <p>{c.text}</p>
              <details className="change-sources">
                <summary>Source values and filings</summary>
                {[
                  { name: 'Current period', value: c.current },
                  { name: 'Prior year', value: c.previous },
                ].map((period) => (
                  <div key={period.name}>
                    <p>
                      {period.name}: {date(period.value.end)} ·{' '}
                      {format(period.value.value, period.value.unit)}
                    </p>
                    {period.value.sources.map((source, i) => (
                      <p className="fine-print" key={i}>
                        <code>{source.tag}</code> · {format(source.value, period.value.unit)} ·{' '}
                        {source.start ? `${date(source.start)} – ` : ''}
                        {date(source.end)}
                      </p>
                    ))}
                  </div>
                ))}
              </details>
            </li>
          ))}
        </ul>
      ) : (
        <p>No comparable financial changes could be validated for this reporting period.</p>
      )}{' '}
    </>
  );
  return (
    <section className="panel thesis-comparison" aria-label="Thesis comparison">
      <div className="section-heading">
        <div>
          <h2>Thesis comparison</h2>
        </div>
        {latest && onAnalyze && (
          <button
            className="button secondary"
            disabled={busy || !detail.thesis}
            onClick={() => onAnalyze(latest.id)}
          >
            {analysis ? 'Compare latest earnings' : 'Compare with latest earnings'}
          </button>
        )}
      </div>
      <ReviewAbout />
      {onAnalyze && <AnalysisQueue />}
      {job && (
        <div className="analysis-progress" role="status" aria-live="polite">
          <p>
            {job.status === 'running' ? 'Reviewing earnings' : 'Comparison queued'}
            {progress?.phase === 'transcript'
              ? ` · Call batches ${progress.completed_batches} of ${progress.total_batches}`
              : progress?.phase === 'filing'
                ? ' · Reviewing the filing'
                : ''}
          </p>
          {job.status === 'queued' && job.error && <p className="fine-print">{job.error}</p>}
          {job.status === 'queued' &&
            job.available_at &&
            new Date(job.available_at).getTime() > Date.now() + 3000 && (
              <p className="fine-print">
                Next attempt at{' '}
                {new Date(job.available_at).toLocaleTimeString([], {
                  hour: 'numeric',
                  minute: '2-digit',
                })}
                . You can keep using the app.
              </p>
            )}
        </div>
      )}
      {!analysis && (
        <p className="muted">
          Save your thesis, then compare it with the latest filing and available earnings call.
        </p>
      )}
      {analysis && (
        <>
          <p className="fine-print">
            {filing?.form} · Reporting period {date(filing?.report_date)}
          </p>
          {stale && (
            <p className="muted">
              Your thesis has changed. Compare again to update the related passages.
            </p>
          )}
          {narrative.length > 0 && (
            <div className="narrative-highlights">
              <h3>From the filing</h3>
              {narrative.map((o, i) => (
                <article key={i}>
                  <blockquote>
                    {o.quote.length > 240
                      ? o.quote.slice(0, 240).replace(/\s+\S*$/, '') + '…'
                      : o.quote}
                  </blockquote>

                  <details>
                    <summary>Thesis link and full passage</summary>
                    <p>Your thesis: “{o.thesis_quote}”</p>
                    <blockquote>{o.quote}</blockquote>
                  </details>
                </article>
              ))}
            </div>
          )}
          {!stale && analysis.result.transcript && (
            <div className="narrative-highlights">
              <h3>
                From the earnings call
                {analysis.result.transcript.quarter
                  ? ` · ${analysis.result.transcript.quarter}`
                  : ''}
              </h3>
              {analysis.result.transcript.status === 'included' ? (
                <>
                  {(analysis.result.transcript.observations ?? []).length === 0 && (
                    <p>No related passages were found in the selected call excerpts.</p>
                  )}
                  {narrativeHighlights(
                    analysis.result.transcript.observations ?? [],
                    detail.thesis?.body ?? '',
                  ).map((o, i) => (
                    <article key={i}>
                      <p className="fine-print">{'speaker' in o ? String(o.speaker) : ''}</p>
                      <blockquote>
                        {o.quote.length > 240
                          ? o.quote.slice(0, 240).replace(/\s+\S*$/, '') + '…'
                          : o.quote}
                      </blockquote>
                      <details>
                        <summary>Thesis link and full passage</summary>
                        <p>Your thesis: “{o.thesis_quote}”</p>
                        <blockquote>{o.quote}</blockquote>
                      </details>
                    </article>
                  ))}
                  {analysis.result.transcript.coverage?.full_transcript && (
                    <p className="fine-print">
                      Full call reviewed · {analysis.result.transcript.coverage.passages_classified}{' '}
                      passages
                    </p>
                  )}
                  <details className="comparison-evidence">
                    <summary>All related call passages and source</summary>
                    {(analysis.result.transcript.observations ?? []).map((o, i) => (
                      <article key={i}>
                        <p className="fine-print">
                          {o.speaker}
                          {o.title ? ` · ${o.title}` : ''}
                        </p>
                        <blockquote>{o.quote}</blockquote>
                        <p>Your thesis: “{o.thesis_quote}”</p>
                      </article>
                    ))}
                    <p className="fine-print">
                      Questions and management statements are attributed to their speakers.
                    </p>
                  </details>
                </>
              ) : (
                <p className="muted">{analysis.result.transcript.reason}</p>
              )}
            </div>
          )}
          {narrative.length > 0 ? (
            <details className="comparison-evidence">
              <summary>Calculated financial changes</summary>
              {financialContent}
            </details>
          ) : (
            <>{financialContent}</>
          )}
          <details className="comparison-evidence">
            <summary>Full model notes and source evidence</summary>
            <p className="fine-print">
              {stale
                ? 'This comparison uses an older thesis.'
                : `Thesis version ${detail.thesis?.version ?? 'unknown'}`}{' '}
              · Selected excerpts only
            </p>
            <p className="error-text">
              These are unverified model notes, not a validated assessment. Supporting quotations
              confirm source text only; they do not establish the interpretation.
            </p>
            {analysis.result.review_notes?.map((note, i) => (
              <p className="error-text" key={i}>
                {note}
              </p>
            ))}
            <p className="fine-print">
              {analysis.model} · {analysis.result.scope}
            </p>
            {analysis.result.observations.map((o, i) => (
              <article className="analysis-card" key={i}>
                <span className="quiet-label">Unverified model assessment: {o.assessment}</span>
                {o.thesis_quote && <p className="fine-print">Thesis claim: “{o.thesis_quote}”</p>}
                {analysis.result.selection_method !== 'complete_passage_classification' && (
                  <p>{o.summary}</p>
                )}
                <blockquote>{o.quote}</blockquote>
              </article>
            ))}
            {analysis.result.rejected_count > 0 && (
              <p>
                {analysis.result.rejected_count} observations failed quote checks and were withheld.
              </p>
            )}
          </details>
          {detail.analyses.length > 1 && (
            <details className="comparison-evidence">
              <summary>Earlier comparisons ({detail.analyses.length - 1})</summary>
              {detail.analyses.slice(1).map((a) => (
                <article key={a.id}>
                  <h3>Comparison #{a.id} · Unverified</h3>
                  <p>{a.result.scope}</p>
                  {a.result.observations.map((o, i) => (
                    <div key={i}>
                      <p>{o.summary}</p>
                      <blockquote>{o.quote}</blockquote>
                    </div>
                  ))}
                </article>
              ))}
            </details>
          )}
        </>
      )}
    </section>
  );
}
