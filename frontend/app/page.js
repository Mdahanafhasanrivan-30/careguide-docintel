'use client';
import Link from 'next/link';
import { useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { useQueryClient } from '@tanstack/react-query';
import { MAX_UPLOAD_MB, uploadFile } from '@/lib/api';
import { Bar, formatBytes } from '@/components/ui';

// The same types the backend accepts (pipeline/detect.py). The server checks again: never trust the browser.
const ACCEPT = {
  'application/pdf': ['.pdf'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
  'image/tiff': ['.tif', '.tiff'],
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
  'application/vnd.ms-excel': ['.xls'],
  'text/csv': ['.csv'],
};
const PARALLEL = 3;   // files uploading at the same time

const LABELS = {
  waiting: 'waiting', uploading: 'uploading', queued: 'queued for processing',
  duplicate: 'already uploaded', rejected: 'rejected', failed: 'upload failed',
};

let nextKey = 0;

function rejectionText(errors) {
  const codes = errors.map((e) => e.code);
  if (codes.includes('file-too-large')) return `larger than ${MAX_UPLOAD_MB} MB`;
  if (codes.includes('file-invalid-type')) return 'file type not accepted';
  return errors.map((e) => e.message).join('; ');
}

export default function UploadPage() {
  const [items, setItems] = useState([]);
  const queryClient = useQueryClient();

  const update = (key, patch) => setItems((all) => all.map((it) => (it.key === key ? { ...it, ...patch } : it)));

  async function uploadAll(batch) {
    const waiting = [...batch];
    async function worker() {
      while (waiting.length) {
        const item = waiting.shift();
        update(item.key, { state: 'uploading' });
        try {
          const result = await uploadFile(item.file, (progress) => update(item.key, { progress }));
          if (result.status === 'rejected') update(item.key, { state: 'rejected', message: result.error });
          else update(item.key, { state: result.already_uploaded ? 'duplicate' : 'queued', progress: 100, id: result.id });
        } catch (e) {
          update(item.key, { state: 'failed', message: e.message });
        }
      }
    }
    await Promise.all(Array.from({ length: PARALLEL }, worker));
    queryClient.invalidateQueries({ queryKey: ['documents'] });   // the list page will show them
  }

  function onDrop(accepted, rejections) {
    const fresh = accepted.map((file) => ({ key: nextKey++, file, state: 'waiting', progress: 0 }));
    const refused = rejections.map(({ file, errors }) => ({
      key: nextKey++, file, state: 'rejected', progress: 0, message: rejectionText(errors),
    }));
    setItems((all) => [...fresh, ...refused, ...all]);
    if (fresh.length) uploadAll(fresh);
  }

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, accept: ACCEPT, maxSize: MAX_UPLOAD_MB * 1024 * 1024, multiple: true,
  });

  const count = (state) => items.filter((it) => it.state === state).length;
  const sent = count('queued') + count('duplicate');

  return (
    <>
      <section className="card">
        <h1>Upload documents</h1>
        <div {...getRootProps({ className: `dropzone ${isDragActive ? 'dragging' : ''}` })}>
          <input {...getInputProps()} />
          <p className="big">{isDragActive ? 'Drop the files here' : 'Drag files here, or click to choose'}</p>
          <p className="muted">PDF, JPG, PNG, TIFF, XLSX, XLS, CSV &middot; up to {MAX_UPLOAD_MB} MB each &middot; many at once</p>
        </div>
      </section>

      {items.length === 0 ? (
        <p className="muted center">Uploaded files are processed in the background: text extraction, AI extraction, then validation.</p>
      ) : (
        <section className="card">
          <div className="row spread">
            <h2>This session</h2>
            <span className="muted">
              {sent} sent &middot; {count('rejected') + count('failed')} not accepted
              {count('uploading') + count('waiting') > 0 && <> &middot; {count('uploading') + count('waiting')} in progress</>}
            </span>
          </div>
          <table>
            <thead><tr><th>File</th><th>Size</th><th>Upload</th><th>Result</th></tr></thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.key}>
                  <td>{it.file.name}</td>
                  <td className="muted">{formatBytes(it.file.size)}</td>
                  <td>{['waiting', 'uploading'].includes(it.state) ? <Bar percent={it.progress} title={`${it.progress}%`} /> : null}</td>
                  <td>
                    <span className={`badge up-${it.state}`}>{LABELS[it.state]}</span>
                    {it.message && <span className="error-text small"> {it.message}</span>}
                    {it.id && <> <Link href={`/documents/${it.id}`}>open</Link></>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {sent > 0 && <p><Link href="/documents">Watch them being processed &rarr;</Link></p>}
        </section>
      )}
    </>
  );
}