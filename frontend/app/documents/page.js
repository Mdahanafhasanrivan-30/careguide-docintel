'use client';
import Link from 'next/link';
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, isBusy } from '@/lib/api';
import { Empty, ErrorBox, formatTime, Loading, Money, PipelineProgress, ReviewFlag, StatusBadge } from '@/components/ui';

const STATUSES = ['', 'queued', 'parsing', 'extracting', 'validating', 'done', 'failed'];

export default function DocumentsPage() {
  const [filters, setFilters] = useState({ status: '', needs_review: '' });
  const queryClient = useQueryClient();

  const docs = useQuery({
    queryKey: ['documents', filters],
    queryFn: () => api.list(filters),
    // Poll every 2 s while anything is still processing; stop when all are finished.
    refetchInterval: (query) => ((query.state.data || []).some((d) => isBusy(d.status)) ? 2000 : false),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['documents'] });
  const reprocess = useMutation({ mutationFn: api.reprocess, onSuccess: refresh });
  const reprocessFailed = useMutation({ mutationFn: api.reprocessFailed, onSuccess: refresh });

  const list = docs.data || [];
  const stats = {
    total: list.length,
    busy: list.filter((d) => isBusy(d.status)).length,
    review: list.filter((d) => d.needs_review).length,
    failed: list.filter((d) => d.status === 'failed').length,
  };
  const set = (name) => (e) => setFilters({ ...filters, [name]: e.target.value });

  return (
    <section className="card">
      <div className="row spread">
        <h1>Documents</h1>
        <div className="row">
          <select value={filters.status} onChange={set('status')} aria-label="Status filter">
            {STATUSES.map((s) => <option key={s} value={s}>{s || 'any status'}</option>)}
          </select>
          <select value={filters.needs_review} onChange={set('needs_review')} aria-label="Review filter">
            <option value="">any review state</option>
            <option value="true">needs review</option>
            <option value="false">no review needed</option>
          </select>
          {stats.failed > 0 && (
            <button onClick={() => reprocessFailed.mutate()} disabled={reprocessFailed.isPending}>
              Reprocess all failed ({stats.failed})
            </button>
          )}
        </div>
      </div>

      {docs.data && (
        <p className="stats">
          <span>{stats.total} shown</span>
          <span className={stats.busy ? 'live' : ''}>{stats.busy} processing{stats.busy ? ' (updating every 2 s)' : ''}</span>
          <span>{stats.review} need review</span>
          <span>{stats.failed} failed</span>
        </p>
      )}

      <ErrorBox error={docs.error || reprocess.error || reprocessFailed.error} onRetry={docs.error ? docs.refetch : undefined} />
      {docs.isPending && <Loading />}
      {docs.data && list.length === 0 && (
        <Empty>No documents match. <Link href="/">Upload some</Link> or change the filters.</Empty>
      )}

      {list.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>File</th><th>Type</th><th>Status</th><th>Review</th><th>Supplier</th>
              <th>Invoice no.</th><th>Date</th><th className="num">Total</th><th>Uploaded</th><th></th>
            </tr>
          </thead>
          <tbody>
            {list.map((d) => (
              <tr key={d.id}>
                <td><Link href={`/documents/${d.id}`}>{d.filename}</Link></td>
                <td className="muted">{d.file_kind || '-'}{d.page_count ? ` · ${d.page_count} p` : ''}</td>
                <td>
                  <StatusBadge status={d.status} />
                  <PipelineProgress status={d.status} />
                  {d.status === 'failed' && <div className="error-text small">{d.error_message}</div>}
                </td>
                <td><ReviewFlag value={d.needs_review} /></td>
                <td>{d.supplier_name || <span className="muted">-</span>}</td>
                <td>{d.invoice_number || <span className="muted">-</span>}</td>
                <td>{d.invoice_date || <span className="muted">-</span>}</td>
                <td className="num"><Money total={d.total} currency={d.currency} /></td>
                <td className="muted small">{formatTime(d.created_at)}</td>
                <td>
                  {d.status === 'failed' && (
                    <button className="small-btn" onClick={() => reprocess.mutate(d.id)} disabled={reprocess.isPending}>Reprocess</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}