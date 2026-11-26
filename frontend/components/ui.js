// Small pieces shared by the pages: badges, states, formatting.
import { isBusy } from '@/lib/api';

const STEPS = ['queued', 'parsing', 'extracting', 'validating', 'done'];

export function StatusBadge({ status }) {
  return <span className={`badge status-${status}`}>{status}</span>;
}

export function Bar({ percent, title }) {
  return (
    <div className="bar" title={title}>
      <div style={{ width: `${Math.max(percent, 4)}%` }} />
    </div>
  );
}

export function PipelineProgress({ status }) {
  // How far along parse -> extract -> validate a document is.
  if (!isBusy(status)) return null;
  const percent = Math.round((STEPS.indexOf(status) / (STEPS.length - 1)) * 100);
  return <Bar percent={percent} title={`${status} (${percent}%)`} />;
}

export function ReviewFlag({ value }) {
  if (value === true) return <span className="badge warn">needs review</span>;
  if (value === false) return <span className="badge ok">ok</span>;
  return <span className="muted">-</span>;
}

export function Money({ total, currency }) {
  if (total === null || total === undefined) return <span className="muted">-</span>;
  return <span className="num">{total} {currency || ''}</span>;
}

export function Loading({ text = 'Loading...' }) {
  return <p className="muted loading">{text}</p>;
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>;
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="error">
      {error.message || String(error)}
      {onRetry && <button className="secondary small-btn" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function formatTime(iso) {
  return iso ? new Date(iso).toLocaleString([], { dateStyle: 'short', timeStyle: 'medium' }) : '';
}

export function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}