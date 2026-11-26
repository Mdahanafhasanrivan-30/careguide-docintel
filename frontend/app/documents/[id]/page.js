'use client';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, isBusy } from '@/lib/api';
import SourcePanel from '@/components/SourcePanel';
import Timeline from '@/components/Timeline';
import { ErrorBox, Loading, PipelineProgress, ReviewFlag, StatusBadge } from '@/components/ui';

// The 8 header fields the backend lets you correct (EDITABLE in services/corrections.py).
const FIELDS = [
  ['invoice_number', 'Invoice number'], ['invoice_date', 'Invoice date'],
  ['supplier_name', 'Supplier'], ['customer_name', 'Customer'],
  ['subtotal', 'Subtotal'], ['tax', 'Tax'], ['total', 'Total'], ['currency', 'Currency'],
];
const ITEM_COLUMNS = ['description', 'quantity', 'unit_price', 'discount', 'amount'];

// Extracted values arrive as {value, raw, evidence, confidence, status}; plain values are allowed too.
const valueOf = (x) => (x !== null && typeof x === 'object' && 'value' in x ? x.value : x);
const show = (x) => (valueOf(x) === null || valueOf(x) === undefined ? '' : String(valueOf(x)));

function confidence(field) {
  const c = field?.confidence;
  if (!field || field.status === 'missing' || c === null || c === undefined) return { level: 'none', label: field?.status || 'missing' };
  return { level: c >= 0.8 ? 'high' : c >= 0.5 ? 'medium' : 'low', label: `${Math.round(c * 100)}%` };
}

function Issues({ issues, onPick }) {
  if (!issues.length) return <p className="ok-text">No validation issues.</p>;
  const editable = new Set(FIELDS.map(([name]) => name));
  return (
    <ul className="issues">
      {issues.map((issue, i) => {
        const canPick = editable.has(issue.field);
        return (
          <li key={i} className={`issue ${issue.severity} ${canPick ? 'pick' : ''}`}
              onClick={canPick ? () => onPick(issue.field) : undefined}
              title={canPick ? 'Click to edit this field' : undefined}>
            <span className={`badge ${issue.severity === 'error' ? 'bad' : 'warn'}`}>{issue.severity}</span>{' '}
            <code>{issue.code}</code>{issue.field && <> on <strong>{issue.field}</strong></>}: {issue.message}
            {(issue.expected || issue.found) && (
              <div className="muted small">expected {issue.expected ?? '-'}, found {issue.found ?? '-'}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export default function DocumentPage() {
  const { id } = useParams();
  const queryClient = useQueryClient();
  const [edits, setEdits] = useState({});          // only the fields the user changed
  const [saved, setSaved] = useState('');
  const [tab, setTab] = useState('original');
  const [evidence, setEvidence] = useState(null);  // text to highlight in the source panel
  const inputs = useRef({});

  const doc = useQuery({
    queryKey: ['document', id],
    queryFn: () => api.get(id),
    refetchInterval: (query) => (isBusy(query.state.data?.status) ? 2000 : false),
  });
  const busy = !doc.data || isBusy(doc.data.status);
  const history = useQuery({
    queryKey: ['history', id],
    queryFn: () => api.history(id),
    refetchInterval: busy ? 2000 : false,
  });

  // When processing finishes, load the final history and text once more.
  const status = doc.data?.status;
  useEffect(() => {
    queryClient.invalidateQueries({ queryKey: ['history', id] });
    queryClient.invalidateQueries({ queryKey: ['text', id] });
  }, [status, id, queryClient]);

  const save = useMutation({
    mutationFn: (fields) => api.correct(id, fields),
    onSuccess: (updated) => {
      queryClient.setQueryData(['document', id], updated);        // show the new version at once
      queryClient.invalidateQueries({ queryKey: ['history', id] });
      queryClient.invalidateQueries({ queryKey: ['documents'] });  // list and search show new values
      queryClient.invalidateQueries({ queryKey: ['search'] });
      setEdits({});
      setSaved(`Saved as version ${updated.version}. Validation ran again: ${updated.issues.length} issue(s) left.`);
    },
  });

  const reprocess = useMutation({
    mutationFn: () => api.reprocess(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['document', id] }),
  });

  if (doc.isPending) return <Loading />;
  if (doc.error) {
    return (
      <section className="card">
        <ErrorBox error={doc.error} onRetry={doc.error.status >= 500 ? doc.refetch : undefined} />
        <Link href="/documents">&larr; All documents</Link>
      </section>
    );
  }

  const d = doc.data;
  const extraction = d.extraction || {};
  const items = extraction.line_items || [];
  const editable = d.status === 'done' && Boolean(d.extraction);
  const changed = Object.keys(edits);
  const errors = d.issues.filter((i) => i.severity === 'error').length;

  function pickField(name) {
    inputs.current[name]?.focus();
    setEvidence(extraction[name]?.evidence || null);
  }

  function submit(e) {
    e.preventDefault();               // Enter in any field saves; no page reload
    setSaved('');
    if (changed.length) save.mutate(edits);
  }

  return (
    <>
      <p><Link href="/documents">&larr; All documents</Link></p>
      <section className="card">
        <div className="row spread">
          <h1>{d.filename}</h1>
          <div className="row">
            <StatusBadge status={d.status} /><PipelineProgress status={d.status} />
            <ReviewFlag value={d.needs_review} />
            {d.version && <span className="muted small">version {d.version} ({d.source})</span>}
          </div>
        </div>
        {d.extraction && (
          <p className="muted">{errors} error(s) and {d.issues.length - errors} warning(s). Click an issue to jump to its field.</p>
        )}
        {d.status === 'failed' && (
          <div className="row">
            <span className="error-text">{d.error_code}: {d.error_message}</span>
            <button onClick={() => reprocess.mutate()} disabled={reprocess.isPending}>Reprocess</button>
          </div>
        )}
        {busy && <p className="muted">Processing... this page updates by itself.</p>}
        <ErrorBox error={reprocess.error} />
      </section>

      <div className="columns">
        <SourcePanel doc={d} tab={tab} setTab={setTab} evidence={evidence} />

        <div>
          {d.extraction && (
            <section className="card">
              <h2>Extracted fields</h2>
              <form onSubmit={submit}>
                <table className="fields">
                  <tbody>
                    {FIELDS.map(([name, label]) => {
                      const field = extraction[name];
                      const conf = confidence(field);
                      return (
                        <tr key={name} className={`conf-${conf.level} ${name in edits ? 'edited' : ''}`}>
                          <th><label htmlFor={`f-${name}`}>{label}</label></th>
                          <td>
                            <input
                              id={`f-${name}`}
                              ref={(el) => { inputs.current[name] = el; }}
                              value={name in edits ? edits[name] : show(field)}
                              disabled={!editable || save.isPending}
                              onFocus={() => setEvidence(field?.evidence || null)}
                              onChange={(e) => setEdits({ ...edits, [name]: e.target.value })}
                            />
                            {field?.evidence && (
                              <button type="button" className="link small"
                                      onClick={() => { setEvidence(field.evidence); setTab('text'); }}>
                                evidence: &ldquo;{field.evidence}&rdquo;
                              </button>
                            )}
                          </td>
                          <td><span className={`badge conf-${conf.level}`} title="model confidence">{conf.label}</span></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <div className="row">
                  <button type="submit" disabled={!changed.length || save.isPending}>
                    {save.isPending ? 'Saving...' : `Save corrections${changed.length ? ` (${changed.length})` : ''}`}
                  </button>
                  {changed.length > 0 && <button type="button" className="secondary" onClick={() => setEdits({})}>Undo</button>}
                  {!editable && <span className="muted small">Fields can be corrected when processing is done.</span>}
                </div>
              </form>
              {saved && <p className="ok-text">{saved}</p>}
              <ErrorBox error={save.error} />
            </section>
          )}

          {d.extraction && (
            <section className="card">
              <h2>Validation issues</h2>
              <Issues issues={d.issues} onPick={pickField} />
            </section>
          )}

          {d.extraction && (
            <section className="card">
              <h2>Line items</h2>
              {items.length === 0 ? <p className="muted">No line items.</p> : (
                <table className="compact">
                  <thead><tr>{ITEM_COLUMNS.map((c) => <th key={c}>{c.replace('_', ' ')}</th>)}</tr></thead>
                  <tbody>
                    {items.map((item, i) => (
                      <tr key={i}>{ITEM_COLUMNS.map((c) => <td key={c}>{show(item[c])}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          )}

          <section className="card">
            <h2>History</h2>
            {history.isPending && <Loading />}
            <ErrorBox error={history.error} onRetry={history.refetch} />
            <Timeline history={history.data} />
          </section>
        </div>
      </div>
    </>
  );
}