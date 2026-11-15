import { useState } from 'react';
import { Plus, X, Pencil, ArrowUpRight } from 'lucide-react';
import { labels, operators, format, instantMetrics, metricUnit } from '../api';
import type { Rule } from '../types';
export type RuleDraft = Omit<Rule, 'id' | 'group_key' | 'version'>;
export default function RuleEditor({
  rules,
  save,
  busy,
}: {
  rules: Rule[];
  save: (draft: RuleDraft, key?: string) => Promise<boolean>;
  busy: boolean;
}) {
  const [editing, setEditing] = useState<Rule | null | undefined>();
  const [draft, setDraft] = useState<RuleDraft>({
    name: '',
    metric: 'revenue_growth',
    operator: 'lt',
    threshold: '5',
    period_kind: 'quarter',
    enabled: true,
  });
  const open = (rule?: Rule) => {
    setEditing(rule ?? null);
    setDraft(
      rule
        ? {
            name: rule.name,
            metric: rule.metric,
            operator: rule.operator,
            threshold: rule.threshold,
            period_kind: rule.period_kind,
            enabled: rule.enabled,
          }
        : {
            name: 'Revenue growth floor',
            metric: 'revenue_growth',
            operator: 'lt',
            threshold: '5',
            period_kind: 'quarter',
            enabled: true,
          },
    );
  };
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <span className="eyebrow">RULES</span>
          <h2>Monitoring rules</h2>
        </div>
        <button className="button secondary" onClick={() => open()}>
          <Plus size={15} />
          Add rule
        </button>
      </div>
      <p className="muted">Choose a metric, reporting period, and threshold for each rule.</p>
      {rules.length === 0 && editing === undefined && (
        <div className="inline-empty">
          <p>No monitoring rules yet.</p>
          <span>Start with revenue growth, margins, or cash generation.</span>
          <button className="text-button" onClick={() => open()}>
            Use a suggested growth rule <ArrowUpRight size={15} />
          </button>
        </div>
      )}
      <div className="rule-list">
        {rules.map((r) => (
          <div className="rule-row" key={r.group_key}>
            <span className={'status-dot ' + (r.enabled ? 'green' : '')} />
            <div className="grow">
              <strong>{r.name}</strong>
              <p>
                {labels[r.metric]} {operators[r.operator]}{' '}
                {format(r.threshold, metricUnit(r.metric))} ·{' '}
                {instantMetrics.has(r.metric) ? 'Instant balance' : r.period_kind} · v{r.version}
              </p>
            </div>
            <span className="quiet-label">{r.enabled ? 'Active' : 'Paused'}</span>
            <button
              className="icon-button"
              title={'Edit ' + r.name}
              aria-label={'Edit ' + r.name}
              onClick={() => open(r)}
            >
              <Pencil size={16} />
            </button>
          </div>
        ))}
      </div>
      {editing !== undefined && (
        <form
          className="rule-form"
          onSubmit={async (e) => {
            e.preventDefault();
            if (await save(draft, editing?.group_key)) setEditing(undefined);
          }}
        >
          <div className="section-heading">
            <strong>{editing ? 'Edit rule' : 'New monitoring rule'}</strong>
            <button
              type="button"
              className="icon-button"
              aria-label="Cancel rule"
              onClick={() => setEditing(undefined)}
            >
              <X size={17} />
            </button>
          </div>
          <label>
            Rule name
            <input
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              required
              maxLength={160}
            />
          </label>
          <div className="form-grid">
            <label>
              Metric
              <select
                value={draft.metric}
                onChange={(e) => setDraft({ ...draft, metric: e.target.value })}
              >
                {Object.entries(labels).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Condition
              <select
                value={draft.operator}
                onChange={(e) => setDraft({ ...draft, operator: e.target.value })}
              >
                {Object.entries(operators).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Threshold ({metricUnit(draft.metric) === '%' ? 'percent' : metricUnit(draft.metric)}
              )
              <input
                type="number"
                step="any"
                required
                value={draft.threshold}
                onChange={(e) => setDraft({ ...draft, threshold: e.target.value })}
              />
            </label>
            <label>
              Reporting period
              <select
                disabled={instantMetrics.has(draft.metric)}
                value={draft.period_kind}
                onChange={(e) => setDraft({ ...draft, period_kind: e.target.value })}
              >
                <option value="quarter">Quarter</option>
                <option value="annual">Annual</option>
              </select>
            </label>
          </div>
          <label className="check-label">
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
            />
            Enable this rule
          </label>
          <div className="form-footer">
            <span>Suggestion only. Choose a threshold that reflects your thesis.</span>
            <button className="button primary" disabled={busy}>
              Save rule
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
