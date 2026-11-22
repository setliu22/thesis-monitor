import type { ThesisClaim } from '../types';

export const driverTitle = (point: ThesisClaim) => (point.driver || point.text).trim();

export function groupThesisPoints(points: ThesisClaim[]) {
  const drivers = new Map<string, Set<string>>();
  for (const point of points) {
    const title = driverTitle(point);
    const checks = drivers.get(title) ?? new Set<string>();
    if (point.driver) checks.add(point.text.trim());
    drivers.set(title, checks);
  }
  return drivers;
}

export default function ThesisPoints({ drivers }: { drivers: Map<string, Set<string>> }) {
  return (
    <ol>
      {[...drivers].map(([driver, checks]) => (
        <li key={driver}>
          {driver}
          {checks.size > 0 && <ul>{[...checks].map((check) => <li key={check}>{check}</li>)}</ul>}
        </li>
      ))}
    </ol>
  );
}
