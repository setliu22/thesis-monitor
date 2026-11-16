import { useState, useEffect, useCallback, useRef } from 'react';
import {
  ArrowDownToLine,
  ArrowUpRight,
  Bell,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  FileText,
  LayoutDashboard,
  LoaderCircle,
  Plus,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Target,
  X,
} from 'lucide-react';
import { api, date } from './api';
import type { Company, Detail, Settings, Rule } from './types';
import CompanyDetail from './components/CompanyDetail';
import RuleEditor, { type RuleDraft } from './components/RuleEditor';
import AlertFeed from './components/AlertFeed';
type View = 'Overview' | 'Thesis & rules' | 'Filings';
const navigation = [
  { name: 'Overview', icon: LayoutDashboard },
  { name: 'Thesis & rules', icon: Target },
  { name: 'Filings', icon: FileText },
] as const;
export default function App() {
  const [companies, setCompanies] = useState<Company[]>([]),
    [selected, setSelected] = useState<number | null>(null),
    [detail, setDetail] = useState<Detail | null>(null),
    [settings, setSettings] = useState<Settings | null>(null);
  const [view, setView] = useState<View>('Overview'),
    [kind, setKind] = useState('quarter'),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(''),
    [message, setMessage] = useState('');
  const [showSettings, setShowSettings] = useState(false),
    [showAdd, setShowAdd] = useState(false),
    [ticker, setTicker] = useState(''),
    [thesis, setThesis] = useState('');
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const loadCompanies = useCallback(async () => {
    const rows = await api<Company[]>('/companies');
    setCompanies(rows);
    setSelected((old) => old ?? rows[0]?.id ?? null);
  }, []);
  useEffect(() => {
    Promise.all([loadCompanies(), api<Settings>('/settings').then(setSettings)])
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [loadCompanies]);
  const reload = useCallback(async () => {
    if (selected === null) return;
    const d = await api<Detail>('/companies/' + selected);
    if (selectedRef.current === selected) setDetail(d);
  }, [selected]);
  useEffect(() => {
    let live = true;
    setDetail(null);
    setThesis('');
    if (selected !== null) {
      api<Detail>('/companies/' + selected)
        .then((d) => {
          if (live) {
            setDetail(d);
            setThesis(d.thesis?.body ?? '');
          }
        })
        .catch((e) => {
          if (live) setError(e.message);
        });
    }
    return () => {
      live = false;
    };
  }, [selected]);
  const running = detail?.jobs.some((j) => j.status === 'running' || j.status === 'queued');
  useEffect(() => {
    if (selected === null) return;
    const refresh = () => {
      if (!document.hidden) reload().catch((e) => setError(e.message));
    };
    const id = setInterval(refresh, running ? 3000 : 15000);
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      clearInterval(id);
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [selected, running, reload]);
  useEffect(() => {
    if (!message) return;
    const id = setTimeout(() => setMessage(''), 6000);
    return () => clearTimeout(id);
  }, [message]);
  async function act(action: () => Promise<void>) {
    setBusy(true);
    setError('');
    try {
      await action();
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong.');
      return false;
    } finally {
      setBusy(false);
    }
  }
  async function saveRule(draft: RuleDraft, key?: string) {
    return await act(async () => {
      await api(
        '/companies/' + selected + '/rules' + (key ? '/' + key : ''),
        key ? 'PUT' : 'POST',
        draft,
      );
      await reload();
      setMessage('Rule saved. Evaluate it against your latest data.');
    });
  }
  function exportBrief() {
    if (!detail) return;
    const blob = new Blob(
      [JSON.stringify({ exported_at: new Date().toISOString(), ...detail }, null, 2)],
      { type: 'application/json' },
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${detail.company.ticker}-thesis-brief.json`;
    link.click();
    URL.revokeObjectURL(url);
    setMessage('Research brief exported.');
  }
  const unread = detail?.alerts.filter((a) => !a.acknowledged_at).length ?? 0;
  const thesisPanel = detail && (
    <section className="panel thesis-panel">
      <div className="section-heading">
        <div>
          <span className="eyebrow">THESIS</span>
          <h2>Investment thesis</h2>
        </div>
        <span className="badge neutral">
          {detail.thesis ? 'Version ' + detail.thesis.version : 'No thesis saved'}
        </span>
      </div>
      <p className="muted">Describe why you own this stock and what would change your view.</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          act(async () => {
            const saved = await api<{ body: string; version: number }>(
              '/companies/' + selected + '/thesis',
              'PUT',
              { body: thesis },
            );
            setThesis(saved.body);
            await reload();
            setMessage('Thesis saved as version ' + saved.version + '.');
          });
        }}
      >
        <label className="sr-only" htmlFor="thesis">
          Your investment thesis
        </label>
        <textarea
          id="thesis"
          value={thesis}
          onChange={(e) => setThesis(e.target.value)}
          required
          maxLength={12000}
          rows={6}
          placeholder="I own this stock because…\n\nWhat would strengthen this view? What would change my mind?"
        />
        <div className="form-footer">
          <span>Every saved revision is preserved.</span>
          <button className="button primary" disabled={busy || !thesis.trim()}>
            Save thesis
          </button>
        </div>
      </form>
    </section>
  );
  const alertPanel = detail && (
    <AlertFeed
      alerts={detail.alerts}
      busy={busy}
      acknowledge={(id) =>
        act(async () => {
          await api('/alerts/' + id + '/acknowledge', 'POST');
          await reload();
          setMessage('Alert marked reviewed.');
        })
      }
    />
  );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setView('Overview');
          }}
        >
          <span className="brand-symbol">
            <Target size={27} />
          </span>
          thesis<span className="brand-period">.</span>
        </a>
        <div className="workspace-label">
          PERSONAL WORKSPACE <ChevronDown size={12} />
        </div>
        <nav aria-label="Main navigation">
          {navigation.map(({ name, icon: Icon }) => (
            <button
              key={name}
              className={'nav-item ' + (view === name ? 'active' : '')}
              onClick={() => setView(name)}
            >
              <Icon size={18} />
              {name}
            </button>
          ))}
        </nav>
        <div className="watchlist-title">
          <span>YOUR WATCHLIST</span>
          <button
            className="icon-button light"
            aria-label="Add company"
            onClick={() => setShowAdd(!showAdd)}
          >
            <Plus size={17} />
          </button>
        </div>
        {showAdd && (
          <form
            className="add-form"
            onSubmit={(e) => {
              e.preventDefault();
              act(async () => {
                const c = await api<Company>('/companies', 'POST', { ticker });
                await loadCompanies();
                setSelected(c.id);
                setTicker('');
                setShowAdd(false);
                setMessage('Company added to your watchlist.');
              });
            }}
          >
            <label className="sr-only" htmlFor="ticker">
              Company ticker
            </label>
            <input
              autoFocus
              id="ticker"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder="US ticker"
              required
              maxLength={12}
            />
            <button className="button primary" disabled={busy}>
              Add
            </button>
          </form>
        )}
        <div className="watchlist">
          {companies.map((c) => (
            <button
              key={c.id}
              className={'watch-company ' + (selected === c.id ? 'selected' : '')}
              onClick={() => setSelected(c.id)}
            >
              <span className="watch-avatar">{c.ticker.slice(0, 1)}</span>
              <span className="grow">
                <strong>{c.ticker}</strong>
                <small>{c.name}</small>
              </span>
              <span className={'status-dot ' + (c.last_success ? 'green' : '')} />
            </button>
          ))}
        </div>
        <div className="sidebar-bottom">
          <div className="source-note">
            <ShieldCheck size={20} />
            <strong>SEC EDGAR data</strong>
            <p>
              Direct from SEC EDGAR.
              <br />
              Source filings linked.
            </p>
            <a
              href="https://www.sec.gov/search-filings/edgar-application-programming-interfaces"
              target="_blank"
              rel="noreferrer"
            >
              About the data <ArrowUpRight size={13} />
            </a>
          </div>
          <button className="nav-item" onClick={() => setShowSettings(true)}>
            <Settings2 size={18} />
            Data settings
          </button>
          <div className="profile">
            <div>ME</div>
            <span>
              Personal investor<small>Local workspace</small>
            </span>
            <span className="status-dot green" />
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            Workspace <ChevronRight size={13} />
            <strong>{view}</strong>
          </div>
          <div className="topbar-right">
            <span className="local-badge">
              <span className="status-dot green" />
              Local workspace
            </span>
            <button
              className="icon-button notification-button"
              aria-label="View alerts"
              onClick={() => {
                setView('Overview');
                window.setTimeout(
                  () => document.getElementById('alerts')?.scrollIntoView({ behavior: 'smooth' }),
                  0,
                );
              }}
            >
              <Bell size={19} />
              {unread > 0 && <i />}
            </button>
            <button
              className="icon-button"
              aria-label="Help and setup"
              onClick={() => setShowSettings(true)}
            >
              <CircleHelp size={19} />
            </button>
          </div>
        </header>
        <main>
          <div className="mobile-watchlist">
            <label>
              Watchlist
              <select
                aria-label="Select company"
                value={selected ?? ''}
                onChange={(e) => setSelected(Number(e.target.value))}
              >
                {companies.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.ticker} · {c.name}
                  </option>
                ))}
              </select>
            </label>
            <button className="button secondary" onClick={() => setShowAdd(!showAdd)}>
              <Plus size={14} />
              Add company
            </button>
          </div>
          {showAdd && (
            <form
              className="mobile-add-form"
              onSubmit={(e) => {
                e.preventDefault();
                act(async () => {
                  const c = await api<Company>('/companies', 'POST', { ticker });
                  await loadCompanies();
                  setSelected(c.id);
                  setTicker('');
                  setShowAdd(false);
                });
              }}
            >
              <label>
                US ticker
                <input
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.toUpperCase())}
                  required
                  maxLength={12}
                />
              </label>
              <button className="button primary" disabled={busy}>
                Add to watchlist
              </button>
            </form>
          )}
          {detail && (
            <p className="fine-print">
              {detail.company.earnings_schedule?.date
                ? `Next earnings: ${date(detail.company.earnings_schedule.date)} · Provider estimate (Alpha Vantage).`
                : 'Next earnings date unavailable.'}{' '}
              {detail.company.earnings_schedule?.error ||
                'Financial data refreshes around the provider date.'}
            </p>
          )}
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                <span className="small-line" /> INVESTMENT MONITOR
              </div>
              <h1>
                {view === 'Overview'
                  ? 'Watchlist overview'
                  : view === 'Thesis & rules'
                    ? 'Thesis & rules'
                    : 'SEC filings'}
              </h1>
              <p>
                {view === 'Overview'
                  ? 'Review financial results, filings, and alerts for your watchlist.'
                  : view === 'Thesis & rules'
                    ? 'Save your investment thesis and set financial thresholds to monitor.'
                    : 'View company filings on SEC EDGAR.'}
              </p>
            </div>
            <div className="page-actions">
              <button className="button secondary" onClick={exportBrief} disabled={!detail}>
                <ArrowDownToLine size={15} />
                Export brief
              </button>
              <button
                className="button primary"
                disabled={busy || running || !detail}
                onClick={() =>
                  !settings?.sec_configured
                    ? setShowSettings(true)
                    : act(async () => {
                        await api('/companies/' + selected + '/refresh', 'POST');
                        await reload();
                        setMessage('Refresh queued. The worker will process it shortly.');
                      })
                }
              >
                {running ? <LoaderCircle size={15} className="spin" /> : <RefreshCw size={15} />}{' '}
                {running ? 'Sync in progress' : 'Refresh SEC data'}
              </button>
            </div>
          </div>
          {error && (
            <div className="notice error" role="alert">
              <span>{error}</span>
              <button
                className="icon-button"
                aria-label="Dismiss error"
                onClick={() => setError('')}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {message && (
            <div className="notice success" role="status">
              <Check size={16} />
              {message}
            </div>
          )}
          {!loading && selected === null && (
            <section className="panel">
              <h2>Add a stock to get started</h2>
              <p>
                Your watchlist starts empty. Search for a US stock ticker to load its SEC filings.
              </p>
              <button className="button primary" onClick={() => setShowAdd(true)}>
                Add company
              </button>
            </section>
          )}
          {loading || (selected !== null && !detail && !error) ? (
            <div className="loading">
              <LoaderCircle className="spin" />
              Opening your workspace…
            </div>
          ) : (
            detail && (
              <>
                <div className="freshness">
                  <span
                    className={
                      'status-dot ' +
                      (detail.company.data_status === 'current' && !detail.company.stale
                        ? 'green'
                        : '')
                    }
                  />
                  <span>
                    {detail.company.data_status === 'current' && !detail.company.stale
                      ? 'Data synced'
                      : detail.company.data_status === 'pending'
                        ? 'New filing found · financial facts pending'
                        : detail.company.last_success
                          ? 'Data may be stale'
                          : 'Awaiting first sync'}
                  </span>
                  <span className="freshness-divider" />
                  <span>Last successful sync: {date(detail.company.last_success)}</span>
                  {detail.company.last_error && (
                    <span className="error-text">{detail.company.last_error}</span>
                  )}
                  <span className="freshness-source">
                    SEC EDGAR <ArrowUpRight size={12} />
                  </span>
                </div>
                {view === 'Overview' && (
                  <>
                    <CompanyDetail
                      detail={detail}
                      kind={kind}
                      setKind={setKind}
                      secConfigured={settings?.sec_configured ?? false}
                      settings={() => setShowSettings(true)}
                    />
                    <div className="overview-lower">
                      <section className="panel thesis-preview">
                        <span className="eyebrow">YOUR INVESTMENT THESIS</span>
                        <h2>Investment thesis</h2>
                        <p>
                          {detail.thesis?.body ||
                            'No thesis saved. Add your reasons for owning this stock.'}
                        </p>
                        <div className="section-heading">
                          <span className="quiet-label">
                            {detail.rules.filter((r) => r.enabled).length} active rules
                          </span>
                          <button className="text-button" onClick={() => setView('Thesis & rules')}>
                            {detail.thesis ? 'Edit thesis & rules' : 'Write your thesis'}{' '}
                            <ArrowUpRight size={15} />
                          </button>
                        </div>
                      </section>
                      {alertPanel}
                    </div>
                  </>
                )}
                {view === 'Thesis & rules' && (
                  <>
                    {thesisPanel}
                    <RuleEditor rules={detail.rules} busy={busy} save={saveRule} />
                    <div className="evaluate-bar">
                      <div>
                        <strong>Evaluate saved rules</strong>
                        <p>Evaluate saved rules against the latest stored reporting period.</p>
                      </div>
                      <button
                        className="button primary"
                        disabled={busy || !detail.rules.some((r) => r.enabled)}
                        onClick={() =>
                          act(async () => {
                            const result = await api<{ created: number }>(
                              '/companies/' + selected + '/evaluate',
                              'POST',
                            );
                            await reload();
                            setMessage(
                              `${result.created} new alert${result.created === 1 ? '' : 's'}. Unavailable metrics cannot trigger alerts.`,
                            );
                          })
                        }
                      >
                        Evaluate rules <ArrowUpRight size={15} />
                      </button>
                    </div>
                  </>
                )}
                {view === 'Filings' && (
                  <>
                    <section className="panel">
                      <div className="section-heading">
                        <div>
                          <span className="eyebrow">PRIMARY SOURCES</span>
                          <h2>Latest company filings.</h2>
                        </div>
                        <span className="badge neutral">{detail.filings.length} filings</span>
                      </div>
                      {detail.filings.length === 0 ? (
                        <div className="inline-empty">
                          <FileText size={27} />
                          <p>Filings will appear after your first sync.</p>
                          <span>We follow 10-K, 10-Q, and 8-K disclosures.</span>
                        </div>
                      ) : (
                        <div className="table-wrap">
                          <table>
                            <thead>
                              <tr>
                                <th>Form</th>
                                <th>Filed</th>
                                <th>Reporting period</th>
                                <th>Accession</th>
                                <th>Actions</th>
                              </tr>
                            </thead>
                            <tbody>
                              {detail.filings.map((f) => (
                                <tr key={f.id}>
                                  <td>
                                    <span className="filing-form">{f.form}</span>
                                  </td>
                                  <td>{date(f.filed)}</td>
                                  <td>{f.report_date ? date(f.report_date) : '—'}</td>
                                  <td>
                                    <code>{f.accession}</code>
                                  </td>
                                  <td>
                                    <div className="line">
                                      {f.url && (
                                        <a
                                          className="text-button"
                                          href={f.url}
                                          target="_blank"
                                          rel="noreferrer"
                                        >
                                          Open <ArrowUpRight size={13} />
                                        </a>
                                      )}
                                      {['10-K', '10-Q', '10-K/A', '10-Q/A'].includes(f.form) && (
                                        <button
                                          className="text-button"
                                          disabled={busy || running}
                                          onClick={() =>
                                            !settings?.llm_configured
                                              ? setShowSettings(true)
                                              : act(async () => {
                                                  await api(
                                                    '/companies/' + selected + '/analyze',
                                                    'POST',
                                                    { filing_id: f.id },
                                                  );
                                                  await reload();
                                                  setMessage(
                                                    'Analysis queued against your saved thesis.',
                                                  );
                                                })
                                          }
                                        >
                                          Analyze
                                        </button>
                                      )}
                                    </div>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </section>
                    <section className="panel">
                      <div className="section-heading">
                        <div>
                          <span className="eyebrow">OPTIONAL ANALYSIS</span>
                          <h2>Filing analysis</h2>
                        </div>
                        <span className="badge neutral">
                          {settings?.llm_configured ? 'Configured' : 'API key needed'}
                        </span>
                      </div>
                      <p className="muted">
                        Analysis covers selected filing excerpts. Supporting quotes are checked
                        against the supplied text; it does not replace reading the full filing.
                      </p>
                      {detail.analyses.length === 0 ? (
                        <p className="fine-print">
                          Save a thesis, then choose Analyze on a periodic filing. Numeric
                          monitoring works independently.
                        </p>
                      ) : (
                        detail.analyses.map((a) => (
                          <article key={a.id} className="analysis-card">
                            <div className="section-heading">
                              <strong>Analysis #{a.id}</strong>
                              <span className="quiet-label">
                                {a.model} · Thesis record #{a.thesis_id}
                              </span>
                            </div>
                            <p className="muted">{a.result.scope}</p>
                            {a.result.observations.map((o, i) => (
                              <div key={i}>
                                <span className="badge neutral">{o.assessment}</span>
                                <p>{o.summary}</p>
                                <blockquote>{o.quote}</blockquote>
                              </div>
                            ))}
                            {a.result.rejected_count > 0 && (
                              <p className="fine-print">
                                {a.result.rejected_count} unsupported observations withheld.
                              </p>
                            )}
                          </article>
                        ))
                      )}
                    </section>
                  </>
                )}
              </>
            )
          )}
          <footer className="page-footer">
            <span>
              <Target size={14} /> thesis. <span className="footer-divider" /> Investment monitor
            </span>
            <span>Source: SEC EDGAR</span>
          </footer>
        </main>
      </div>
      {showSettings && (
        <div className="modal-backdrop" onClick={() => setShowSettings(false)}>
          <section
            className="settings-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="settings-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="section-heading">
              <span className="eyebrow">DATA CONNECTION</span>
              <button
                className="icon-button"
                autoFocus
                aria-label="Close settings"
                onClick={() => setShowSettings(false)}
              >
                <X size={20} />
              </button>
            </div>
            <h2 id="settings-title">SEC data settings</h2>
            <p>
              SEC EDGAR provides the filings and financial facts. Automated requests need a contact
              identity.
            </p>
            <div className="setup-status">
              <ShieldCheck size={20} />
              <strong>
                {settings?.sec_configured ? 'SEC identity configured' : 'SEC identity required'}
              </strong>
            </div>
            <ol>
              <li>
                Copy <code>.env.example</code> to <code>.env</code> in the project folder.
              </li>
              <li>
                Set your own name and a real contact email:
                <pre>SEC_USER_AGENT=Your Name your@email.com</pre>
              </li>
              <li>Restart the API and worker, reload this page, then refresh SEC data.</li>
            </ol>
            <hr />
            <h3>Earnings calendar</h3>
            <p>
              Get an Alpha Vantage API key and set <code>ALPHAVANTAGE_API_KEY</code> on the server,
              then restart the API and SEC worker. The same calendar covers every watched ticker.
              Dates are provider estimates; missing dates are shown as unavailable.
            </p>
            <h3>Email alerts</h3>
            <p>
              Create a Resend account. For testing, its default sender can email your Resend account
              address. For regular sending, verify a domain. Add these server environment variables:
            </p>
            <pre>
              ALERT_EMAIL=your@email.com{'\n'}EMAIL_FROM=your verified sender{'\n'}
              RESEND_API_KEY=your API key
            </pre>
            <p>
              Restart the API and email worker. For alerts while your computer is off, deploy the
              prepared Render services. Keep the API key on the server.
            </p>
            <h3>Optional filing analysis</h3>
            <p>
              Set <code>OPENAI_API_KEY</code> on the server to enable model observations. Selected
              filing excerpts and your saved thesis will be sent to the model provider when you
              request analysis.
            </p>
            <p className="fine-print">
              Financial data refreshes around earnings. The worker checks for a newly announced date
              once a day. Email alerts require a running server, a Resend API key and a verified
              sender.
            </p>
            <button className="button primary" onClick={() => setShowSettings(false)}>
              Got it <Check size={15} />
            </button>
          </section>
        </div>
      )}
    </div>
  );
}
