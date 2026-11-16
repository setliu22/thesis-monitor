import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  ArrowUpRight,
  Bell,
  CalendarDays,
  X,
  DollarSign,
  Landmark,
  Flame,
  BriefcaseBusiness,
  ChartColumnIncreasing,
  Vote,
} from 'lucide-react';
import { api } from '../api';
const categories = {
  earnings: 'Earnings',
  fed: 'Federal Reserve',
  inflation: 'Inflation',
  employment: 'Jobs',
  gdp: 'GDP',
  election: 'Elections',
};
type Category = keyof typeof categories;
const categoryIcons = {
  earnings: DollarSign,
  fed: Landmark,
  inflation: Flame,
  employment: BriefcaseBusiness,
  gdp: ChartColumnIncreasing,
  election: Vote,
};
const shortLabels = {
  earnings: 'Earn',
  fed: 'Fed',
  inflation: 'Infl',
  employment: 'Jobs',
  gdp: 'GDP',
  election: 'Vote',
};
function EventMarker({ category }: { category: Category }) {
  const Icon = categoryIcons[category];
  return <Icon className={'event-marker ' + category} size={14} aria-hidden="true" />;
}
type Event = {
  id: number;
  title: string;
  category: Category;
  day: string;
  starts_at: string | null;
  source_url: string;
  status: string;
  notes: string;
  ticker: string | null;
};
type Response = {
  events: Event[];
  missing_earnings: { ticker: string; name: string }[];
  sources: {
    provider: string;
    checked_at: string | null;
    error: string | null;
    source_label?: string | null;
  }[];
};
type Prefs = {
  enabled: boolean;
  days: number[];
  categories: Category[];
  hour: number;
  email_configured: boolean;
  timezone: string;
};
const today = () =>
  new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
const iso = (d: Date) => d.toISOString().slice(0, 10);
const dateLabel = (d: string) =>
  new Intl.DateTimeFormat('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(d + 'T00:00:00Z'));
export default function InvestmentCalendar() {
  const [month, setMonth] = useState(today().slice(0, 7)),
    [selected, setSelected] = useState(today()),
    [data, setData] = useState<Response | null>(null),
    [filters, setFilters] = useState<Category[]>(Object.keys(categories) as Category[]),
    [invested, setInvested] = useState(true),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(true),
    [prefs, setPrefs] = useState<Prefs | null>(null),
    [edit, setEdit] = useState(false),
    [saving, setSaving] = useState(false);
  const [year, m] = month.split('-').map(Number);
  const days = useMemo(() => {
    const first = new Date(Date.UTC(year, m - 1, 1));
    first.setUTCDate(1 - first.getUTCDay());
    return Array.from({ length: 42 }, (_, i) => {
      const d = new Date(first);
      d.setUTCDate(d.getUTCDate() + i);
      return iso(d);
    });
  }, [year, m]);
  const load = useCallback(
    () => api<Response>(`/calendar?start=${days[0]}&end=${days[41]}&invested_only=${invested}`),
    [days, invested],
  );
  useEffect(() => {
    let live = true;
    setLoading(true);
    load()
      .then((d) => {
        if (live) {
          setData(d);
          setError('');
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    const timer = window.setInterval(() => {
      if (!document.hidden)
        load()
          .then((d) => {
            if (live) setData(d);
          })
          .catch(() => {});
    }, 60000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [load]);
  useEffect(() => {
    api<Prefs>('/reminder-settings')
      .then(setPrefs)
      .catch((e) => setError(e.message));
  }, []);
  const events = (data?.events ?? []).filter((e) => filters.includes(e.category));
  const dayEvents = events.filter((e) => e.day === selected);
  const upcoming = events.filter((e) => e.day >= today()).slice(0, 5);
  function selectDay(day: string) {
    setSelected(day);
    if (window.matchMedia('(max-width: 600px)').matches)
      window.setTimeout(
        () =>
          document
            .getElementById('day-agenda')
            ?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
        0,
      );
  }
  function shift(n: number) {
    const d = new Date(Date.UTC(year, m - 1 + n, 1));
    setMonth(iso(d).slice(0, 7));
    setSelected(iso(d));
  }
  async function save() {
    if (!prefs) return;
    setSaving(true);
    try {
      setPrefs(
        await api<Prefs>('/reminder-settings', 'PUT', {
          enabled: prefs.enabled,
          days: prefs.days,
          categories: prefs.categories,
          hour: prefs.hour,
        }),
      );
      setEdit(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save reminders');
    } finally {
      setSaving(false);
    }
  }
  return (
    <section className="investment-calendar">
      <div className="calendar-intro">
        <div>
          <span className="eyebrow">YOUR INVESTMENT CALENDAR</span>
          <h1>Investment calendar</h1>
          <p>Earnings dates and market events.</p>
        </div>
        <button className="button secondary" onClick={() => setEdit(true)}>
          <Bell size={16} /> Reminders
        </button>
      </div>
      {error && (
        <p role="alert" className="notice error">
          {error}
        </p>
      )}
      <div className="calendar-workspace">
        <div className="calendar-board">
          <div className="calendar-toolbar">
            <div className="calendar-month-title">
              <h2>
                {new Intl.DateTimeFormat('en-US', {
                  month: 'long',
                  year: 'numeric',
                  timeZone: 'UTC',
                }).format(new Date(Date.UTC(year, m - 1, 1)))}
              </h2>
              <input
                aria-label="Jump to month"
                type="month"
                value={month}
                onChange={(e) => {
                  if (e.target.value) {
                    setMonth(e.target.value);
                    setSelected(e.target.value + '-01');
                  }
                }}
              />
            </div>
            <div className="calendar-navigation">
              <button
                className="text-button"
                onClick={() => {
                  setMonth(today().slice(0, 7));
                  setSelected(today());
                }}
              >
                Today
              </button>
              <button className="icon-button" aria-label="Previous month" onClick={() => shift(-1)}>
                <ChevronLeft size={18} />
              </button>
              <button className="icon-button" aria-label="Next month" onClick={() => shift(1)}>
                <ChevronRight size={18} />
              </button>
            </div>
          </div>
          <div className="calendar-legend">
            {Object.entries(categories).map(([key, label]) => (
              <label key={key}>
                <input
                  type="checkbox"
                  checked={filters.includes(key as Category)}
                  onChange={() =>
                    setFilters((f) =>
                      f.includes(key as Category)
                        ? f.filter((k) => k !== key)
                        : [...f, key as Category],
                    )
                  }
                />
                <EventMarker category={key as Category} />
                {label}
              </label>
            ))}
          </div>
          <div className="calendar-weekdays" aria-hidden="true">
            {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => (
              <span key={d}>{d}</span>
            ))}
          </div>
          <div className="calendar-grid" aria-label="Monthly events calendar">
            {days.map((day) => {
              const items = events.filter((e) => e.day === day);
              return (
                <button
                  key={day}
                  aria-label={`${dateLabel(day)}, ${items.length} scheduled events`}
                  aria-pressed={day === selected}
                  className={
                    'calendar-cell ' +
                    (day.slice(0, 7) !== month ? 'outside ' : '') +
                    (day === selected ? 'selected ' : '') +
                    (day === today() ? 'today' : '')
                  }
                  onClick={() => selectDay(day)}
                >
                  <span className="calendar-date">{Number(day.slice(-2))}</span>
                  <span className="calendar-cell-events">
                    {items.slice(0, 3).map((e) => (
                      <span key={e.id} className={'calendar-event ' + e.category} title={e.title}>
                        <EventMarker category={e.category} />
                        <span className="calendar-event-name">{e.ticker || e.title}</span>
                        <span className="calendar-event-short">{shortLabels[e.category]}</span>
                      </span>
                    ))}
                    {items.length > 3 && <small>+{items.length - 3} more</small>}
                  </span>
                </button>
              );
            })}
          </div>
          <div className="calendar-foot">
            <span>
              {loading ? 'Loading scheduled events…' : `${events.length} events in this view`}
            </span>
            <label>
              <input
                type="checkbox"
                checked={invested}
                onChange={(e) => setInvested(e.target.checked)}
              />{' '}
              Investments only
            </label>
          </div>
        </div>
        <aside className="calendar-agenda" id="day-agenda">
          <div className="agenda-date">
            <CalendarDays size={18} />
            <span>{dateLabel(selected)}</span>
          </div>
          {!dayEvents.length ? (
            <div className="agenda-empty">
              <CalendarDays size={26} />
              <p>No scheduled events</p>
              <span>Select another day or browse upcoming events.</span>
            </div>
          ) : (
            dayEvents.map((e) => (
              <article key={e.id} className={'agenda-event ' + e.category}>
                <span className="event-category">
                  <EventMarker category={e.category} />
                  {categories[e.category]}
                </span>
                <h3>{e.title}</h3>
                <p>
                  {e.starts_at
                    ? new Intl.DateTimeFormat('en-US', {
                        timeZone: 'America/New_York',
                        hour: 'numeric',
                        minute: '2-digit',
                      }).format(new Date(e.starts_at)) + ' ET'
                    : 'Date only · Eastern Time'}
                </p>
                <span className="badge neutral">
                  {e.status === 'estimated'
                    ? 'Estimated date'
                    : e.status === 'statutory'
                      ? 'Statutory date'
                      : 'Published schedule'}
                </span>
                <a className="text-button" href={e.source_url} target="_blank" rel="noreferrer">
                  View source <ArrowUpRight size={13} />
                </a>
              </article>
            ))
          )}
          <div className="agenda-upcoming">
            <span className="eyebrow">COMING UP</span>
            {upcoming.length ? (
              upcoming.map((e) => (
                <button key={e.id} onClick={() => setSelected(e.day)}>
                  <span className="upcoming-day">
                    {new Intl.DateTimeFormat('en-US', {
                      month: 'short',
                      day: 'numeric',
                      timeZone: 'UTC',
                    }).format(new Date(e.day + 'T00:00:00Z'))}
                  </span>
                  <EventMarker category={e.category} />
                  <span>{e.title}</span>
                </button>
              ))
            ) : (
              <p className="muted">No upcoming events in this view.</p>
            )}
          </div>
        </aside>
      </div>
      {!!data?.missing_earnings.length && (
        <p className="calendar-data-note">
          Earnings dates not yet available: {data.missing_earnings.map((c) => c.ticker).join(', ')}.
          No dates have been guessed.
        </p>
      )}
      <details className="calendar-source-status">
        <summary>
          Sources & coverage {data?.sources.some((s) => s.error) ? '· Some feeds unavailable' : ''}
        </summary>
        {data?.sources.map((s) => (
          <p key={s.provider}>
            <strong>{s.source_label || s.provider.replace('events-', '').toUpperCase()}</strong> —{' '}
            {s.error || 'Schedule loaded'}
            {s.checked_at
              ? ` · Checked ${new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric' }).format(new Date(s.checked_at))}`
              : ''}
          </p>
        ))}
        <p>
          Published dates can change. This calendar does not predict event outcomes or market moves.
        </p>
      </details>
      <p className="fine-print">
        {prefs?.enabled
          ? `Email reminders: ${prefs.days.join(' and ')} days before, at ${prefs.hour}:00 Eastern.`
          : 'Email reminders are off.'}{' '}
        {!prefs?.email_configured ? 'Email provider setup is incomplete.' : ''}
      </p>
      {edit && prefs && (
        <div className="modal-backdrop">
          <section
            className="modal calendar-reminder-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="reminder-title"
          >
            <div className="section-heading">
              <h2 id="reminder-title">Event reminders</h2>
              <button
                className="icon-button"
                aria-label="Close reminders"
                onClick={() => setEdit(false)}
              >
                <X size={18} />
              </button>
            </div>
            <label className="check-label">
              <input
                type="checkbox"
                checked={prefs.enabled}
                onChange={(e) => setPrefs({ ...prefs, enabled: e.target.checked })}
              />
              Email me before scheduled events
            </label>
            <h3>When</h3>
            <div className="reminder-options">
              {[14, 7, 1].map((n) => (
                <label key={n}>
                  <input
                    type="checkbox"
                    checked={prefs.days.includes(n)}
                    onChange={() =>
                      setPrefs({
                        ...prefs,
                        days: prefs.days.includes(n)
                          ? prefs.days.filter((d) => d !== n)
                          : [...prefs.days, n].sort((a, b) => b - a),
                      })
                    }
                  />
                  {n === 7 ? 'One week' : n === 1 ? 'One day' : 'Two weeks'} before
                </label>
              ))}
            </div>
            <label className="reminder-hour">
              Delivery time (Eastern)
              <select
                value={prefs.hour}
                onChange={(e) => setPrefs({ ...prefs, hour: Number(e.target.value) })}
              >
                {Array.from({ length: 24 }, (_, i) => (
                  <option key={i} value={i}>
                    {String(i).padStart(2, '0')}:00
                  </option>
                ))}
              </select>
            </label>
            <h3>Events</h3>
            <div className="reminder-options">
              {Object.entries(categories).map(([key, label]) => (
                <label key={key}>
                  <input
                    type="checkbox"
                    checked={prefs.categories.includes(key as Category)}
                    onChange={() =>
                      setPrefs({
                        ...prefs,
                        categories: prefs.categories.includes(key as Category)
                          ? prefs.categories.filter((c) => c !== key)
                          : [...prefs.categories, key as Category],
                      })
                    }
                  />
                  {label}
                </label>
              ))}
            </div>
            <p className="fine-print">
              Reminders need the server and email worker running. Changed or removed events cancel
              pending reminders. Past reminders are not backfilled.
            </p>
            <button
              className="button primary"
              disabled={saving || !prefs.days.length}
              onClick={save}
            >
              {saving ? 'Saving…' : 'Save reminders'}
            </button>
          </section>
        </div>
      )}
    </section>
  );
}
