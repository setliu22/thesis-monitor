import { useEffect, useState } from 'react';
import { api } from '../api';

type GroqAllowance = {
  tokens_remaining: number | null;
  tokens_reset_at: number | null;
  requests_remaining: number | null;
  requests_reset_at: number | null;
};

function allowanceText(label: string, remaining: number | null, resetAt: number | null) {
  if (remaining == null) return `${label}: no reading yet`;
  if (resetAt && resetAt * 1000 <= Date.now())
    return `${label}: window reset · awaiting next reading`;
  const count = `${label}: ${remaining.toLocaleString()} left`;
  return resetAt ? `${count} · resets at ${new Date(resetAt * 1000).toLocaleTimeString()}` : count;
}

export default function AnalysisQueue() {
  const [label, setLabel] = useState('Checking analysis queue…');
  const [groq, setGroq] = useState<GroqAllowance | null>(null);
  useEffect(() => {
    let active = true;
    async function refresh() {
      if (document.hidden) return;
      try {
        const { queued, running, groq } = await api<{
          queued: number;
          running: number;
          groq?: GroqAllowance;
        }>('/analysis-queue');
        if (typeof queued !== 'number' || typeof running !== 'number') {
          throw new Error('Invalid queue counts');
        }
        if (active) {
          setLabel(`Analysis queue: ${queued} waiting · ${running} running`);
          setGroq(groq ?? null);
        }
      } catch {
        if (active) {
          setLabel('Analysis queue unavailable');
          setGroq(null);
        }
      }
    }
    void refresh();
    const interval = window.setInterval(refresh, 5000);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      active = false;
      window.clearInterval(interval);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, []);
  return (
    <div className="fine-print">
      <p aria-live="polite">{label}</p>
      {groq && (
        <div aria-label="Groq allowance">
          <div>
            Groq ·{' '}
            {allowanceText('Tokens this minute', groq.tokens_remaining, groq.tokens_reset_at)}
          </div>
          <div>
            {allowanceText('Requests today', groq.requests_remaining, groq.requests_reset_at)}
          </div>
        </div>
      )}
    </div>
  );
}
