'use client';
import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { ErrorBox, Loading } from '@/components/ui';

// What the browser can show by itself. TIFF and spreadsheets have no preview: the text tab shows them.
function viewKind(filename) {
  const name = filename.toLowerCase();
  if (name.endsWith('.pdf')) return 'pdf';
  if (/\.(png|jpe?g)$/.test(name)) return 'image';
  return 'none';
}

const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

// Find the evidence in the text even if line breaks or spaces differ (OCR often splits lines).
function findEvidence(text, evidence) {
  const words = (evidence || '').trim().split(/\s+/).filter(Boolean);
  if (!words.length) return null;
  const match = new RegExp(words.map(escape).join('\\s+'), 'i').exec(text);
  return match ? { start: match.index, end: match.index + match[0].length } : null;
}

function DocumentText({ text, evidence }) {
  const markRef = useRef(null);
  const hit = findEvidence(text, evidence);
  useEffect(() => {
    markRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [evidence, hit?.start]);

  if (!text) return <p className="muted">No text was extracted from this document.</p>;
  return (
    <>
      {evidence && !hit && <p className="muted small">The evidence &ldquo;{evidence}&rdquo; was not found word for word in the text.</p>}
      <pre className="doc-text">
        {hit ? (
          <>
            {text.slice(0, hit.start)}
            <mark ref={markRef}>{text.slice(hit.start, hit.end)}</mark>
            {text.slice(hit.end)}
          </>
        ) : text}
      </pre>
    </>
  );
}

export default function SourcePanel({ doc, tab, setTab, evidence }) {
  const kind = viewKind(doc.filename);
  const hasText = !['queued', 'parsing'].includes(doc.status);
  const text = useQuery({ queryKey: ['text', doc.id], queryFn: () => api.text(doc.id), enabled: hasText });
  const shown = kind === 'none' ? 'text' : tab;

  return (
    <section className="card source">
      <div className="row spread">
        <div className="tabs">
          {kind !== 'none' && (
            <button className={shown === 'original' ? 'tab active' : 'tab'} onClick={() => setTab('original')}>Original</button>
          )}
          <button className={shown === 'text' ? 'tab active' : 'tab'} onClick={() => setTab('text')}>Extracted text</button>
        </div>
        <a href={api.fileUrl(doc.id)} target="_blank" rel="noreferrer" className="small">Open file</a>
      </div>

      {shown === 'original' && kind === 'pdf' && (
        <iframe src={api.fileUrl(doc.id)} title={`Original of ${doc.filename}`} className="viewer" />
      )}
      {shown === 'original' && kind === 'image' && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={api.fileUrl(doc.id)} alt={`Original of ${doc.filename}`} className="viewer-img" />
      )}
      {shown === 'text' && (
        <>
          {!hasText && <p className="muted">The text appears after parsing.</p>}
          {text.isPending && hasText && <Loading />}
          <ErrorBox error={text.error} onRetry={text.refetch} />
          {text.data && <DocumentText text={text.data.text} evidence={evidence} />}
          {text.data?.truncated && <p className="muted small">Showing the first {text.data.text.length.toLocaleString()} of {text.data.length.toLocaleString()} characters.</p>}
        </>
      )}
    </section>
  );
}