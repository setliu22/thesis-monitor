import ThesisComparison from './components/ThesisComparison';
import ThesisHistory from './components/ThesisHistory';
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  CalendarDays,
  ArrowDownToLine,
  ArrowUpRight,
  Bell,
  Check,
  LayoutDashboard,
  LoaderCircle,
  Plus,
  RefreshCw,
  Trash2,
  ShieldCheck,
  Target,
  X,
} from 'lucide-react';
import { api, date } from './api';
import type { Company, Detail, Settings, Rule, ThesisVersion } from './types';
import InvestmentCalendar from './components/InvestmentCalendar';
import CompanySearch, { type SearchResult } from './components/CompanySearch';
import CompanyDetail from './components/CompanyDetail';
import RuleEditor, { type RuleDraft } from './components/RuleEditor';
import AlertFeed from './components/AlertFeed';
type View = 'Calendar' | 'Metrics & rules' | 'Thesis';
const navigation = [
  { name: 'Calendar', icon: CalendarDays },
  { name: 'Metrics & rules', icon: LayoutDashboard },
  { name: 'Thesis', icon: Target },
] as const;
export default function App() {
  const [companies, setCompanies] = useState<Company[]>([]),
    [selected, setSelected] = useState<number | null>(null),
    [detail, setDetail] = useState<Detail | null>(null),
    [settings, setSettings] = useState<Settings | null>(null);
  const [view, setView] = useState<View>('Calendar'),
    [kind, setKind] = useState('quarter'),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(''),
    [message, setMessage] = useState('');
  const [showSettings, setShowSettings] = useState(false),
    [showAdd, setShowAdd] = useState(false),
    [showThesisHistory, setShowThesisHistory] = useState(false),
    [thesis, setThesis] = useState('');
  const [calendarSelection, setCalendarSelection] = useState<number | null | undefined>();
  const calendarCompany =
    calendarSelection === null
      ? null
      : companies.some((company) => company.id === calendarSelection)
        ? (calendarSelection ?? selected)
        : selected;
  const [watchlistLoaded, setWatchlistLoaded] = useState(false);
  const detailKey = selected;
  const activeDetailKey = useRef(detailKey);
  activeDetailKey.current = detailKey;
  const detailRequest = useRef(0);
  const thesisCompany = useRef<number | null>(null);
  const loadCompanies = useCallback(async () => {
    const rows = await api<Company[]>('/companies');
    setCompanies(rows);
    setWatchlistLoaded(true);
    setSelected((old) => (rows.some((c) => c.id === old) ? old : (rows[0]?.id ?? null)));
  }, []);
  useEffect(() => {
    loadCompanies()
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
    api<Settings>('/settings')
      .then(setSettings)
      .catch((e) => setError(e.message));
  }, [loadCompanies]);
  const reload = useCallback(async () => {
    if (selected === null || activeDetailKey.current !== detailKey) return;
    const request = ++detailRequest.current;
    const isCurrent = () =>
      activeDetailKey.current === detailKey && request === detailRequest.current;
    try {
      const d = await api<Detail>('/companies/' + selected);
      if (!isCurrent()) return;
      if (thesisCompany.current !== selected) {
        thesisCompany.current = selected;
        setThesis(d.thesis?.body ?? '');
      }
      setDetail(d);
    } catch (e) {
      if (isCurrent()) throw e;
    }
  }, [detailKey, selected]);
  useEffect(() => {
    thesisCompany.current = null;
    setThesis('');
    setShowThesisHistory(false);
    setDetail(null);
  }, [selected]);
  useEffect(() => {
    reload().catch((e) => setError(e.message));
  }, [reload]);
  const activeJobs =
    detail?.jobs.filter((j) => j.status === 'running' || j.status === 'queued') ?? [];
  const refreshing = activeJobs.some(
    (j) => j.kind === 'refresh' && j.payload?.waiting_for !== 'groq',
  );
  const refreshJob = activeJobs.find(
    (job) => job.kind === 'refresh' && job.payload?.waiting_for !== 'groq',
  );
  const refreshProgress = refreshJob?.payload?.progress;
  const analyzing = activeJobs.some((j) => j.kind === 'analysis');
  const nextJobCheck = activeJobs.reduce((soonest, job) => {
    const available = job.available_at ? Date.parse(job.available_at) : NaN;
    if (job.status === 'running' || !Number.isFinite(available)) return 0;
    return Math.min(soonest, available);
  }, Infinity);
  useEffect(() => {
    if (selected === null) return;
    let timer: ReturnType<typeof setTimeout>;
    let stopped = false;
    let pending = false;
    const schedule = () => {
      const delay = Math.max(3000, Math.min(60000, nextJobCheck - Date.now()));
      timer = setTimeout(refresh, delay);
    };
    const refresh = async () => {
      if (stopped || pending) return;
      clearTimeout(timer);
      if (document.hidden) {
        schedule();
        return;
      }
      pending = true;
      try {
        await reload();
      } catch (e) {
        if (!stopped) setError(e instanceof Error ? e.message : String(e));
      } finally {
        pending = false;
        if (!stopped) schedule();
      }
    };
    // Company detail carries financial history. Back off while jobs await a retry.
    schedule();
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      stopped = true;
      clearTimeout(timer);
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [selected, nextJobCheck, reload]);
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
  async function addCompany(row: SearchResult) {
    await act(async () => {
      const c = await api<Company>('/companies', 'POST', { ticker: row.ticker });
      await loadCompanies();
      setSelected(c.id);
      setShowAdd(false);
      setView('Metrics & rules');
      setMessage('Company added to your watchlist.');
    });
  }
  async function removeCompany(company: Company) {
    await act(async () => {
      await api('/companies/' + company.id, 'DELETE');
      if (selected === company.id) setDetail(null);
      await loadCompanies();
      setMessage(company.ticker + ' removed. Add it again to restore its saved data.');
    });
  }
  async function saveRule(draft: RuleDraft, key?: string) {
    return await act(async () => {
      await api(
        '/companies/' + selected + '/rules' + (key ? '/' + key : ''),
        key ? 'PUT' : 'POST',
        draft,
      );
      await reload();
      setMessage('Rule saved. The latest stored period was checked.');
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
  const compareFiling = (filingId: number, rerun = false, retryConnection = false) => {
    if (!settings?.llm_configured) {
      setShowSettings(true);
      return;
    }
    act(async () => {
      const response = await api<{ cached?: boolean; status?: string }>(
        '/companies/' + selected + '/analyze',
        'POST',
        { filing_id: filingId, rerun, retry_connection: retryConnection },
      );
      await reload();
      setMessage(
        retryConnection
          ? response.status === 'connection_retry_not_needed'
            ? 'Review status updated.'
            : 'Connection retry requested.'
          : response.cached
            ? 'Showing your saved comparison.'
            : 'Comparison queued against your saved thesis.',
      );
    });
  };
  const unread = detail?.alerts.filter((a) => !a.acknowledged_at).length ?? 0;
  const thesisPanel = detail && (
    <section className="panel thesis-panel">
      <div className="section-heading">
        <h2>Investment thesis</h2>
        <button
          type="button"
          className="text-button"
          aria-expanded={showThesisHistory}
          onClick={() => setShowThesisHistory((open) => !open)}
        >
          {showThesisHistory ? 'Hide history' : 'History'}
        </button>
      </div>
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
          placeholder="I own this stock because…"
        />
        <div className="form-footer thesis-save">
          <button className="button primary" disabled={busy || !thesis.trim()}>
            Save thesis
          </button>
        </div>
      </form>
      {showThesisHistory && (
        <ThesisHistory
          key={selected}
          companyId={selected!}
          currentThesisId={detail.thesis?.id}
          onDeleted={async (current: ThesisVersion | null, deletedCurrent: boolean) => {
            if (deletedCurrent) {
              setThesis(current?.body ?? '');
              await reload();
            }
            setMessage(deletedCurrent ? 'Thesis history updated.' : 'Thesis version deleted.');
          }}
        />
      )}
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
            setView('Metrics & rules');
          }}
        >
          <span className="brand-symbol">
            <Target size={27} />
          </span>
          thesis<span className="brand-period">.</span>
        </a>
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
          <div className="add-form">
            <CompanySearch disabled={busy} onSelect={addCompany} />
          </div>
        )}
        <div className="watchlist">
          {companies.map((c) => (
            <div className={`watch-row ${selected === c.id ? 'selected' : ''}`} key={c.id}>
              <button
                className={'watch-company ' + (selected === c.id ? 'selected' : '')}
                onClick={() => {
                  setSelected(c.id);
                  setCalendarSelection(c.id);
                }}
              >
                <span className="watch-avatar">{c.ticker.slice(0, 1)}</span>
                <span className="grow">
                  <strong>{c.ticker}</strong>
                  <small>{c.name}</small>
                </span>
                <span className={'status-dot ' + (c.last_success ? 'green' : '')} />
              </button>
              <button
                className="watch-remove"
                aria-label={'Remove ' + c.ticker + ' from watchlist'}
                title={'Remove ' + c.ticker + ' from watchlist'}
                disabled={busy}
                onClick={() => void removeCompany(c)}
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <strong>{view}</strong>
          </div>
          <div className="topbar-right">
            <button
              className="icon-button notification-button"
              aria-label="View alerts"
              onClick={() => {
                setView('Metrics & rules');
                window.setTimeout(
                  () => document.getElementById('alerts')?.scrollIntoView({ behavior: 'smooth' }),
                  0,
                );
              }}
            >
              <Bell size={19} />
              {unread > 0 && <i />}
            </button>
          </div>
        </header>
        <main>
          <div className="mobile-watchlist">
            {view !== 'Calendar' && (
              <label>
                Watchlist
                <select
                  aria-label="Select company"
                  value={selected ?? ''}
                  onChange={(e) => {
                    const id = e.target.value ? Number(e.target.value) : null;
                    if (id !== null) setSelected(id);
                  }}
                >
                  {companies.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.ticker} · {c.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <button className="button secondary" onClick={() => setShowAdd(!showAdd)}>
              <Plus size={14} />
              Add company
            </button>
          </div>
          {showAdd && (
            <div className="mobile-add-form">
              <CompanySearch disabled={busy} onSelect={addCompany} />
            </div>
          )}
          {view === 'Calendar' ? (
            <InvestmentCalendar
              watchlistVersion={companies.map((c) => `${c.id}:${c.invested}`).join(',')}
              companies={companies.map(({ id, ticker, name }) => ({ id, ticker, name }))}
              selectedCompanyId={calendarCompany}
              onContextCompanyChange={setCalendarSelection}
            />
          ) : (
            <>
              {detail && (
                <div className="company-status-bar">
                  <label className="holding-toggle">
                    <input
                      type="checkbox"
                      checked={detail.company.invested ?? true}
                      onChange={(e) => {
                        const invested = e.target.checked;
                        void act(async () => {
                          await api('/companies/' + selected + '/holding', 'PUT', { invested });
                          await loadCompanies();
                          await reload();
                        });
                      }}
                    />
                    {(detail.company.invested ?? true)
                      ? 'Invested in this stock'
                      : 'Following only'}
                  </label>
                  <button
                    className="text-button remove-company-button"
                    disabled={busy}
                    onClick={() => void removeCompany(detail.company)}
                  >
                    <Trash2 size={14} /> Remove from watchlist
                  </button>
                </div>
              )}
              {view === 'Metrics & rules' && detail?.company.earnings_schedule?.date && (
                <p className="earnings-status">
                  Estimated earnings date · {date(detail.company.earnings_schedule.date)}
                </p>
              )}
              <div className="page-heading">
                <div>
                  <h1>{view}</h1>
                </div>
                <div className="page-actions">
                  <button className="button secondary" onClick={exportBrief} disabled={!detail}>
                    <ArrowDownToLine size={15} />
                    Export brief
                  </button>
                  <button
                    className="button primary"
                    disabled={busy || refreshing || !detail}
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
                    {refreshing ? (
                      <LoaderCircle size={15} className="spin" />
                    ) : (
                      <RefreshCw size={15} />
                    )}{' '}
                    {refreshing ? 'Sync in progress' : 'Refresh SEC data'}
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
              {!loading && watchlistLoaded && selected === null && (
                <section className="panel">
                  <h2>Add a stock to get started</h2>
                  <p>
                    Your watchlist starts empty. Search for a US stock ticker to load its SEC
                    filings.
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
                    {detail.company.last_error ? (
                      <p className="error-text" role="status">
                        Sync error · {detail.company.last_error}
                      </p>
                    ) : detail.company.data_status === 'pending' ? (
                      <p role="status">New filing found. Financial figures are pending.</p>
                    ) : detail.company.stale && detail.company.last_success ? (
                      <p role="status">Financial data may be out of date.</p>
                    ) : null}
                    {refreshing && (
                      <div className="sync-progress" role="status" aria-live="polite">
                        <p>
                          {refreshProgress?.phase
                            ? `Syncing ${refreshProgress.phase} · ${refreshProgress.completed_batches} of ${refreshProgress.total_batches}`
                            : 'Syncing company data'}
                        </p>
                        <progress
                          value={refreshProgress?.completed_batches}
                          max={refreshProgress?.total_batches || 4}
                        />
                      </div>
                    )}
                    {view === 'Metrics & rules' && (
                      <>
                        <CompanyDetail
                          detail={detail}
                          kind={kind}
                          setKind={setKind}
                          secConfigured={settings?.sec_configured ?? false}
                          settings={() => setShowSettings(true)}
                        />
                        <RuleEditor rules={detail.rules} busy={busy} save={saveRule} />
                        {detail.rules.some((rule) => rule.enabled) && (
                          <div className="evaluate-bar">
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
                              Re-check rules <ArrowUpRight size={15} />
                            </button>
                          </div>
                        )}
                        {alertPanel}
                      </>
                    )}
                    {view === 'Thesis' && (
                      <>
                        {thesisPanel}
                        <ThesisComparison
                          detail={detail}
                          busy={Boolean(busy || (!detail.review && analyzing))}
                          onAnalyze={compareFiling}
                          onSummaryQueued={settings?.llm_configured ? reload : undefined}
                        />
                      </>
                    )}
                  </>
                )
              )}
            </>
          )}
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
            <h3>Optional earnings analysis</h3>
            <p>
              Set <code>GROQ_API_KEY</code> on the server to enable filing analysis. Selected filing
              excerpts, available earnings-call excerpts and your saved thesis will be sent to Groq
              when you request analysis.
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
