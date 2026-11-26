'use client';
import Link from 'next/link';
import { useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Empty, ErrorBox, Loading, Money, ReviewFlag, StatusBadge } from '@/components/ui';

const EMPTY = {
  q: '', mode: 'hybrid', supplier: '', currency: '', date_from: '', date_to: '',
  min_total: '', max_total: '', needs_review: '',
};
const MODES = [
  ['hybrid', 'Hybrid', 'both, merged by rank'],
  ['keyword', 'Keyword', 'exact words and numbers'],
  ['semantic', 'Semantic', 'same meaning, other words'],
];

// Keyword snippets mark matched words as [word]; show them highlighted.
function Snippet({ text }) {
  if (!text) return null;
  const parts = text.split(/\[([^\]]+)\]/);    // odd positions are the matched words
  return <p className="snippet">{parts.map((p, i) => (i % 2 ? <mark key={i}>{p}</mark> : p))}</p>;
}

export default function SearchPage() {
  const [form, setForm] = useState(EMPTY);
  const [submitted, setSubmitted] = useState(null);   // the search that is shown

  const results = useQuery({
    queryKey: ['search', submitted],
    queryFn: () => api.search({ ...submitted, limit: 50 }),
    enabled: submitted !== null,
    placeholderData: keepPreviousData,     // keep old results visible while the new ones load
  });

  const set = (name) => (e) => setForm({ ...form, [name]: e.target.value });
  const run = (next) => { setForm(next); setSubmitted(next); };

  function submit(e) {
    e.preventDefault();             // stop the browser from reloading the page
    setSubmitted({ ...form });
  }

  const data = results.data;
  const unavailable = results.error?.status === 503;

  return (
    <>
      <section className="card">
        <h1>Search</h1>
        <form onSubmit={submit}>
          <div className="row">
            <input className="grow" aria-label="Search text" value={form.q} onChange={set('q')}
                   placeholder='Words, "exact phrase", invoice number... (empty = filters only)' />
            <button type="submit" disabled={results.isFetching}>{results.isFetching ? 'Searching...' : 'Search'}</button>
          </div>
          <div className="segmented" role="radiogroup" aria-label="Search mode">
            {MODES.map(([value, label, hint]) => (
              <button type="button" key={value} role="radio" aria-checked={form.mode === value}
                      className={form.mode === value ? 'active' : ''} title={hint}
                      onClick={() => setForm({ ...form, mode: value })}>
                {label}
              </button>
            ))}
            <span className="muted small">{MODES.find(([v]) => v === form.mode)[2]}</span>
          </div>
          <div className="row filters">
            <input placeholder="Supplier contains" aria-label="Supplier" value={form.supplier} onChange={set('supplier')} />
            <input placeholder="Currency" aria-label="Currency" value={form.currency} onChange={set('currency')} size={6} />
            <label>From <input type="date" value={form.date_from} onChange={set('date_from')} /></label>
            <label>To <input type="date" value={form.date_to} onChange={set('date_to')} /></label>
            <input type="number" step="0.01" placeholder="Min total" aria-label="Min total" value={form.min_total} onChange={set('min_total')} />
            <input type="number" step="0.01" placeholder="Max total" aria-label="Max total" value={form.max_total} onChange={set('max_total')} />
            <select value={form.needs_review} onChange={set('needs_review')} aria-label="Review state">
              <option value="">any review state</option>
              <option value="true">needs review</option>
              <option value="false">no review needed</option>
            </select>
            <button type="button" className="secondary" onClick={() => { setForm(EMPTY); setSubmitted(null); }}>Reset</button>
          </div>
        </form>
      </section>

      <section className="card">
        {submitted === null && (
          <Empty>Type words, or leave the box empty and set filters, then press Search.</Empty>
        )}
        {results.isPending && submitted !== null && <Loading text="Searching..." />}
        <ErrorBox error={results.error} />
        {unavailable && (
          <button className="secondary" onClick={() => run({ ...form, mode: 'keyword' })}>Search in keyword mode instead</button>
        )}
        {data && !results.error && (
          <>
            <p className="muted">{data.count} result(s) &middot; mode: {data.mode}{data.query && <> &middot; &ldquo;{data.query}&rdquo;</>}</p>
            {data.count === 0 && <Empty>No documents match. Try other words, another mode, or fewer filters.</Empty>}
            {data.hits.map(({ document: d, score, snippet }) => (
              <div key={d.id} className="hit">
                <div className="row spread">
                  <Link href={`/documents/${d.id}`}><strong>{d.filename}</strong></Link>
                  <span className="muted small">score {score}</span>
                </div>
                <div className="row small">
                  <StatusBadge status={d.status} /><ReviewFlag value={d.needs_review} />
                  <span>{d.supplier_name || '-'}</span><span>{d.invoice_number || '-'}</span>
                  <span>{d.invoice_date || '-'}</span><Money total={d.total} currency={d.currency} />
                </div>
                <Snippet text={snippet} />
              </div>
            ))}
          </>
        )}
      </section>
    </>
  );
}