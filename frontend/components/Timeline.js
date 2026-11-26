import { formatTime } from '@/components/ui';

// Processing history: one dot per event (upload, parse, extract, validate, index, correct, reprocess).
export default function Timeline({ history }) {
  if (!history) return null;
  const total = history.events.reduce((sum, e) => sum + (e.duration_ms || 0), 0);
  return (
    <>
      <h3>Versions</h3>
      <ul className="versions">
        {history.versions.map((v) => (
          <li key={v.version}>
            <strong>v{v.version}</strong> {v.source === 'ai' ? 'AI extraction' : 'manual correction'}
            {' '}&middot; {v.issue_count} issue(s) &middot; <span className="muted">{formatTime(v.created_at)}</span>
            {v.changes?.map((c) => (
              <div key={c.field} className="change">{c.field}: <del>{c.old ?? 'empty'}</del> &rarr; <ins>{c.new ?? 'empty'}</ins></div>
            ))}
          </li>
        ))}
        {history.versions.length === 0 && <li className="muted">No extraction yet.</li>}
      </ul>

      <h3>Processing history <span className="muted small">({(total / 1000).toFixed(1)} s of measured work)</span></h3>
      <ol className="timeline">
        {history.events.map((e, i) => (
          <li key={i} className={`ev-${e.status}`}>
            <div className="row spread">
              <span><strong>{e.stage}</strong> <span className={`badge ev-${e.status}`}>{e.status}</span></span>
              <span className="muted small">{e.duration_ms !== null ? `${e.duration_ms} ms · ` : ''}{formatTime(e.created_at)}</span>
            </div>
            {e.message && <div className="small">{e.message}</div>}
          </li>
        ))}
      </ol>
    </>
  );
}