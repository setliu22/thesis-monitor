import { useEffect, useId, useState } from 'react';
import { Search } from 'lucide-react';
import { api } from '../api';
export type SearchResult = { ticker: string; name: string; exchange: string };
export default function CompanySearch({
  onSelect,
  disabled = false,
}: {
  onSelect: (value: SearchResult) => void;
  disabled?: boolean;
}) {
  const [query, setQuery] = useState(''),
    [rows, setRows] = useState<SearchResult[]>([]),
    [loading, setLoading] = useState(false),
    [error, setError] = useState(''),
    [active, setActive] = useState(0),
    [open, setOpen] = useState(false);
  const id = useId();
  useEffect(() => {
    let live = true;
    if (!query.trim()) {
      setRows([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError('');
    const timer = window.setTimeout(() => {
      api<SearchResult[]>('/company-search?q=' + encodeURIComponent(query.trim()))
        .then((results) => {
          if (live) {
            setRows(results);
            setActive(0);
          }
        })
        .catch((e) => {
          if (live) {
            setRows([]);
            setError(e.message);
          }
        })
        .finally(() => {
          if (live) setLoading(false);
        });
    }, 250);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [query]);
  function choose(row: SearchResult) {
    onSelect(row);
    setQuery('');
    setRows([]);
    setOpen(false);
  }
  return (
    <div className="company-search">
      <label className="search-input">
        <Search size={16} />
        <input
          aria-label="Search ticker or company"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={open && !!query}
          aria-controls={id}
          aria-activedescendant={open && rows[active] ? `${id}-${active}` : undefined}
          placeholder="Ticker or company name"
          autoComplete="off"
          value={query}
          disabled={disabled}
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault();
              setActive((i) => Math.min(i + 1, rows.length - 1));
            }
            if (e.key === 'ArrowUp') {
              e.preventDefault();
              setActive((i) => Math.max(0, i - 1));
            }
            if (e.key === 'Escape') setOpen(false);
            if (e.key === 'Enter') {
              e.preventDefault();
              if (rows[active]) choose(rows[active]);
            }
          }}
        />
      </label>
      {open && query && (
        <div className="search-results" id={id} role="listbox" aria-label="Matching companies">
          {loading && <p role="status">Searching companies…</p>}
          {error && <p role="alert">{error}</p>}
          {!loading && !error && !rows.length && <p>No matching companies</p>}
          {rows.map((r, i) => (
            <button
              type="button"
              role="option"
              aria-selected={i === active}
              id={`${id}-${i}`}
              key={r.ticker}
              className={i === active ? 'highlighted' : ''}
              onMouseEnter={() => setActive(i)}
              onClick={() => choose(r)}
            >
              <strong>{r.ticker}</strong>
              <span>{r.name}</span>
              <small>{r.exchange}</small>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
