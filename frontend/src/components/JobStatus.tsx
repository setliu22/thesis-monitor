import { CheckCircle2, Clock3, AlertTriangle, LoaderCircle } from 'lucide-react';
import type { Job } from '../types';
import { date } from '../api';
export default function JobStatus({ jobs }: { jobs: Job[] }) {
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <span className="eyebrow">DATA REFRESHES</span>
          <h2>Sync history</h2>
        </div>
        <Clock3 size={21} />
      </div>
      {jobs.length === 0 ? (
        <div className="inline-empty">
          <p>No jobs yet.</p>
          <span>Your refresh history will appear here.</span>
        </div>
      ) : (
        jobs.map((j) => (
          <div className="job-row" key={j.id}>
            <span className={'job-icon ' + j.status}>
              {j.status === 'succeeded' ? (
                <CheckCircle2 size={19} />
              ) : j.status === 'failed' ? (
                <AlertTriangle size={19} />
              ) : (
                <LoaderCircle size={19} className={j.status === 'running' ? 'spin' : ''} />
              )}
            </span>
            <div className="grow">
              <strong>
                {j.kind === 'refresh' ? 'SEC data refresh' : 'Filing analysis'}{' '}
                <span className="quiet-label">#{j.id}</span>
              </strong>
              <p>
                {date(j.created_at)} · Attempt {j.attempts}
                {j.error && <span className="error-text">{j.error}</span>}
              </p>
            </div>
            <span className="badge neutral">{j.status}</span>
          </div>
        ))
      )}
    </section>
  );
}
