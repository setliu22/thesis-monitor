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

export default function ThesisComparison({
  detail,
  busy,
  onAnalyze,
}: {
  detail: Detail;
  busy: boolean;
  onAnalyze: (filingId: number) => void;
}) {
  const analysis = detail.analyses[0];
  const latest = detail.filings.find((f) => ['10-K', '10-Q', '10-K/A', '10-Q/A'].includes(f.form));
  const filing = detail.filings.find((f) => f.id === analysis?.filing_id);
  const sourceUrl = filing?.url || analysis?.result.source_url;
  const stale = Boolean(analysis && detail.thesis && analysis.thesis_id !== detail.thesis.id);
  const changes = analysis ? financialChanges(detail, analysis.filing_id) : [];
  return (
    <section className="panel thesis-comparison" aria-label="Thesis comparison">
      <div className="section-heading">
        <div>
          <h2>Thesis comparison</h2>
        </div>
        {latest && (
          <button
            className="button secondary"
            disabled={busy || !detail.thesis}
            onClick={() => onAnalyze(latest.id)}
          >
            {analysis ? 'Compare latest filing' : 'Compare with latest filing'}
          </button>
        )}
      </div>
      {!analysis && (
        <p className="muted">
          Save your thesis, then compare it with the latest quarterly or annual filing.
        </p>
      )}
      {analysis && (
        <>
          <p className="fine-print">
            {filing?.form} · Reporting period {date(filing?.report_date)}
          </p>
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
                            {date(source.end)}{' '}
                            {source.url && (
                              <a
                                className="text-button"
                                href={source.url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                Source filing ↗
                              </a>
                            )}
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
                <p>{o.summary}</p>
                <blockquote>{o.quote}</blockquote>
                {sourceUrl && (
                  <a className="text-button" href={sourceUrl} target="_blank" rel="noreferrer">
                    Source filing ↗
                  </a>
                )}
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
                  {(a.result.source_url ||
                    detail.filings.find((f) => f.id === a.filing_id)?.url) && (
                    <a
                      className="text-button"
                      href={
                        a.result.source_url ||
                        detail.filings.find((f) => f.id === a.filing_id)!.url!
                      }
                      target="_blank"
                      rel="noreferrer"
                    >
                      Source filing ↗
                    </a>
                  )}
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
