import { useId, useState } from 'react';
import type { Observation } from '../types';
import { date, format, labels } from '../api';

export default function Trend({
  points,
  metric,
  compact = false,
  count = 16,
}: {
  points: Observation[];
  metric: string;
  compact?: boolean;
  count?: number;
}) {
  const id = useId().replaceAll(':', '');
  const [hover, setHover] = useState<number | null>(null);
  const valid = points
    .filter((p) => p.value !== null && Number.isFinite(Number(p.value)))
    .sort((a, b) => a.end.localeCompare(b.end))
    .slice(-count);
  if (valid.length < 2)
    return (
      <div className={compact ? 'mini-chart-empty' : 'chart-empty'}>
        {valid.length ? 'One period available' : 'Historical data unavailable'}
      </div>
    );
  const values = valid.map((p) => Number(p.value));
  const min = Math.min(...values),
    max = Math.max(...values);
  const pad = (max - min || Math.abs(min) || 1) * 0.12;
  const low = min - pad,
    high = max + pad;
  const times = valid.map((p) => Date.parse(p.end + 'T00:00:00Z'));
  const coords = values.map((v, i) => [
    20 + ((times[i] - times[0]) / (times.at(-1)! - times[0] || 1)) * 560,
    148 - ((v - low) / (high - low)) * 120,
  ]);
  const path = coords.map(([x, y], i) => `${i ? 'L' : 'M'}${x},${y}`).join(' ');
  return (
    <div className={compact ? 'metric-sparkline' : 'trend'}>
      {!compact && (
        <p className="chart-readout">
          {hover !== null
            ? `${date(valid[hover].end)} · ${format(valid[hover].value, valid[hover].unit)}`
            : `${format(valid.at(-1)!.value, valid.at(-1)!.unit)} · ${date(valid.at(-1)!.end)}`}
        </p>
      )}
      <svg
        viewBox="0 0 600 180"
        role="img"
        aria-label={`${labels[metric]} historical trend, ${date(valid[0].end)} to ${date(valid.at(-1)!.end)}`}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#91ac68" stopOpacity=".25" />
            <stop offset="100%" stopColor="#91ac68" stopOpacity="0" />
          </linearGradient>
        </defs>
        {!compact &&
          [30, 90, 150].map((y) => (
            <line key={y} x1="20" x2="580" y1={y} y2={y} stroke="#e4e9e2" strokeDasharray="3 5" />
          ))}
        <path d={path + ' L580,165 L20,165 Z'} fill={`url(#${id})`} />
        <path
          d={path}
          fill="none"
          stroke="#4a6945"
          strokeWidth={compact ? 6 : 2.5}
          strokeLinecap="round"
        />
        {coords.map(([x, y], i) => (
          <circle
            key={valid[i].end}
            cx={x}
            cy={y}
            r={compact ? 4 : hover === i ? 6 : 4}
            fill="#fff"
            stroke="#4a6945"
            strokeWidth="2"
            tabIndex={compact ? undefined : 0}
            onMouseEnter={() => setHover(i)}
            onFocus={() => setHover(i)}
            aria-label={`${date(valid[i].end)}: ${format(valid[i].value, valid[i].unit)}`}
          >
            <title>
              {date(valid[i].end)}: {format(valid[i].value, valid[i].unit)}
            </title>
          </circle>
        ))}
      </svg>
      <div className="chart-labels">
        <span>{date(valid[0].end)}</span>
        <span>{date(valid.at(-1)!.end)}</span>
      </div>
    </div>
  );
}
