import { useId, useState, type PointerEvent } from 'react';
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
  const change = values.at(-1)! - values[0];
  const direction = change > 0 ? 'Increased' : change < 0 ? 'Decreased' : 'Unchanged';
  const color = '#526879';
  const min = Math.min(...values),
    max = Math.max(...values);
  const pad = (max - min || Math.abs(min) || 1) * 0.12;
  const low = min - pad,
    high = max + pad;
  const left = compact ? 20 : 108;
  const right = 580;
  const top = 20;
  const bottom = 148;
  const times = valid.map((p) => Date.parse(p.end + 'T00:00:00Z'));
  const coords = values.map((v, i) => [
    left + ((times[i] - times[0]) / (times.at(-1)! - times[0] || 1)) * (right - left),
    bottom - ((v - low) / (high - low)) * (bottom - top),
  ]);
  const activePoint = hover === null ? undefined : valid[hover];
  const selectNearest = (event: PointerEvent<SVGRectElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    if (!bounds.width) return;
    const x = left + ((event.clientX - bounds.left) / bounds.width) * (right - left);
    const nearest = coords.reduce(
      (best, [pointX], index) =>
        Math.abs(pointX - x) < Math.abs(coords[best][0] - x) ? index : best,
      0,
    );
    setHover(nearest);
  };
  const path = coords.map(([x, y], i) => `${i ? 'L' : 'M'}${x},${y}`).join(' ');
  return (
    <div className={compact ? 'metric-sparkline' : 'trend'}>
      <svg
        viewBox="0 0 600 180"
        role="img"
        aria-label={`${labels[metric]} historical trend. ${direction} over the displayed period, ${date(valid[0].end)} to ${date(valid.at(-1)!.end)}.`}
        onPointerLeave={(event) => {
          if (event.pointerType !== 'touch') setHover(null);
        }}
      >
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity=".22" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        {!compact &&
          [0, 0.5, 1].map((fraction) => {
            const y = top + fraction * (bottom - top);
            return (
              <g key={fraction}>
                <line x1={left} x2={right} y1={y} y2={y} stroke="#dce4da" />
                <text x={left - 10} y={y} dominantBaseline="middle" textAnchor="end">
                  {format(String(high - (high - low) * fraction), valid[0].unit)}
                </text>
              </g>
            );
          })}
        <path d={path + ` L${right},${bottom} L${left},${bottom} Z`} fill={`url(#${id})`} />
        <path
          d={path}
          fill="none"
          stroke={color}
          strokeWidth={compact ? 6 : 2.5}
          strokeLinecap="round"
        />
        {!compact && coords.map(([x, y], i) => (
          <circle
            key={valid[i].end}
            cx={x}
            cy={y}
            r={hover === i ? 6 : 5}
            opacity={hover === i ? 1 : 0}
            fill="#fff"
            stroke={color}
            strokeWidth="2"
            tabIndex={0}
            onFocus={() => setHover(i)}
            onBlur={() => setHover(null)}
            aria-label={`${date(valid[i].end)}: ${format(valid[i].value, valid[i].unit)}`}
          />
        ))}
        {!compact && (
          <g>
            <rect
              x={left}
              y={top}
              width={right - left}
              height={bottom - top}
              fill="transparent"
              onPointerMove={selectNearest}
              onPointerDown={selectNearest}
            />
            <text x={left} y="174">{date(valid[0].end)}</text>
            <text x={right} y="174" textAnchor="end">{date(valid.at(-1)!.end)}</text>
          </g>
        )}
      </svg>
      {!compact && activePoint && (
        <div className="trend-tooltip" role="tooltip">
          {date(activePoint.end)} · <strong>{format(activePoint.value, activePoint.unit)}</strong>
        </div>
      )}
    </div>
  );
}
