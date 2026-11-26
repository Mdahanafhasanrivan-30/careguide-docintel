"""End-to-end evaluation: upload the labelled files through the real API, wait for the worker,
then score the AI extraction of every file against its label and print a Markdown report.

    dcrun python scripts/run_eval.py                    # all files in eval_data
    dcrun python scripts/run_eval.py --limit 2          # quick check: 2 invoices = 4 files
    dcrun python scripts/run_eval.py --no-upload        # score again without uploading

Files uploaded earlier are not sent again (same bytes = same document), so a second run
costs no Gemini calls. Manual corrections are ignored: the AI version is scored.
"""
import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Document, Extraction, ProcessingEvent  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.evaluation.scoring import FIELDS, pct, percentile, score_fields, score_line_items  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / 'eval_data'
API_URL = os.environ.get('EVAL_API_URL', 'http://api:8000')
BUSY = {'queued', 'parsing', 'extracting', 'validating'}
BATCH = 10                      # files per upload request (the API allows 20)
STAGES = ['parse', 'extract', 'validate', 'index']

# Invoices that are wrong on purpose (Phase 2 dataset), so the validator SHOULD flag them:
# 005 missing tax, 009 wrong total, 013 no currency, 017 no customer, 021 duplicate number.
PLANTED_ERRORS = {'inv_005', 'inv_009', 'inv_013', 'inv_017', 'inv_021'}


def files_to_run(limit: int | None, kind: str) -> list[tuple[Path, Path, str]]:
    """(file, label, kind) for every labelled invoice; kind is 'pdf' or 'scan'."""
    out = []
    labels = sorted(DATA.glob('inv_*.json'))[:limit] if limit else sorted(DATA.glob('inv_*.json'))
    for label in labels:
        for path, k in ((label.with_suffix('.pdf'), 'pdf'),
                        (label.with_name(f'{label.stem}_scan.jpg'), 'scan')):
            if path.exists() and kind in (k, 'both'):
                out.append((path, label, k))
    return out


def upload(paths: list[Path]) -> dict[str, dict]:
    key = os.environ.get('API_KEY', '')
    if not key:
        sys.exit('API_KEY is not set in this container (check .env)')
    results = {}
    with httpx.Client(base_url=API_URL, headers={'X-API-Key': key}, timeout=120) as client:
        for i in range(0, len(paths), BATCH):
            chunk = paths[i:i + BATCH]
            files = [('files', (p.name, p.read_bytes(), 'application/octet-stream')) for p in chunk]
            response = client.post('/api/v1/documents', files=files)
            response.raise_for_status()
            for path, result in zip(chunk, response.json()):
                results[path.name] = result
    return results


def wait(ids: list, timeout_min: int) -> float:
    """Poll the database until no document is busy. Returns the seconds waited."""
    started = time.monotonic()
    while True:
        with SessionLocal() as db:
            statuses = Counter(db.scalars(select(Document.status).where(Document.id.in_(ids))).all())
        busy = sum(n for s, n in statuses.items() if s in BUSY)
        waited = time.monotonic() - started
        print(f'  {int(waited):>4} s  done {statuses.get("done", 0)}  failed {statuses.get("failed", 0)}'
              f'  still busy {busy}', file=sys.stderr)
        if busy == 0:
            return waited
        if waited > timeout_min * 60:
            print(f'  stopped waiting after {timeout_min} min; busy files count as not finished', file=sys.stderr)
            return waited
        time.sleep(10)


def collect(db, ids_by_name: dict[str, object]) -> dict[str, dict]:
    """Per file: status, error, the latest AI extraction, its issues, and the stage timings."""
    out = {}
    for name, doc_id in ids_by_name.items():
        doc = db.get(Document, doc_id)
        ai = db.scalar(select(Extraction).where(Extraction.document_id == doc_id, Extraction.source == 'ai')
                       .order_by(Extraction.version.desc()).limit(1))
        events = db.scalars(select(ProcessingEvent).where(ProcessingEvent.document_id == doc_id)
                            .order_by(ProcessingEvent.created_at, ProcessingEvent.id)).all()
        stage_ms = {}
        for e in events:                                  # the last successful run of each stage
            if e.status == 'ok' and e.duration_ms is not None and e.stage in STAGES:
                stage_ms[e.stage] = e.duration_ms
        upload_at = next((e.created_at for e in events if e.stage == 'upload'), None)
        finished_at = max((e.created_at for e in events if e.stage in ('validate', 'index') and e.status == 'ok'),
                          default=None)
        out[name] = {
            'status': doc.status, 'error_code': doc.error_code, 'attempts': doc.attempts,
            'data': ai.data if ai else None,
            'issues': [i.get('code') for i in (ai.issues if ai else [])],
            'needs_review': ai.needs_review if ai else None,
            'stage_ms': stage_ms,
            'retries': sum(1 for e in events if e.status == 'retry'),
            'end_to_end_s': (finished_at - upload_at).total_seconds() if upload_at and finished_at else None,
        }
    return out


def ms(v) -> str:
    return '-' if v is None else (f'{v / 1000:.1f} s' if v >= 1000 else f'{int(v)} ms')


def report(rows: list[dict], new_names: set[str], waited: float) -> str:
    lines = [f'# Evaluation run, {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC', '']
    total = len(rows)
    done = [r for r in rows if r['status'] == 'done' and r['data'] is not None]
    failed = [r for r in rows if r['status'] == 'failed']
    unfinished = [r for r in rows if r['status'] in BUSY]

    lines += ['## Success and failure', '', '| Measure | Value |', '| --- | --- |',
              f'| Files evaluated | {total} ({sum(r["kind"] == "pdf" for r in rows)} PDF, '
              f'{sum(r["kind"] == "scan" for r in rows)} scans) |',
              f'| Processed successfully (done) | {pct(len(done), total)} |',
              f'| Failed | {pct(len(failed), total)} |',
              f'| Not finished when the run stopped | {pct(len(unfinished), total)} |',
              f'| Files that needed an automatic retry | {pct(sum(r["retries"] > 0 for r in rows), total)} |', '']
    if failed:
        lines += ['Failed files: ' + ', '.join(f'{r["file"]} ({r["error_code"]})' for r in failed), '']

    lines += ['## Field accuracy (AI version, compared with the label)', '',
              '| Field | PDF | Scan | All |', '| --- | --- | --- | --- |']
    for f in FIELDS + ['line_items']:
        cells = []
        for group in ('pdf', 'scan', None):
            rs = [r for r in done if group in (None, r['kind'])]
            cells.append(pct(sum(r['score'][f] for r in rs), len(rs)))
        lines.append(f'| {f} | ' + ' | '.join(cells) + ' |')
    lines += ['', '| Overall | Fields correct | Documents with all 8 fields correct |', '| --- | --- | --- |']
    for group, label in (('pdf', 'PDF'), ('scan', 'Scan'), (None, 'All')):
        rs = [r for r in done if group in (None, r['kind'])]
        right = sum(sum(r['score'][f] for f in FIELDS) for r in rs)
        lines.append(f'| {label} | {pct(right, len(rs) * len(FIELDS))} | '
                     f'{pct(sum(all(r["score"][f] for f in FIELDS) for r in rs), len(rs))} |')
    lines.append('')

    wrong = [(r['file'], f) for r in done for f in FIELDS + ['line_items'] if not r['score'][f]]
    lines += ['### Every wrong field', '']
    lines += [f'- {name}: {field}' for name, field in wrong] or ['- none']
    lines.append('')

    lines += ['## Processing time per stage (successful files)', '',
              '| Stage | Files | Average | p50 | p95 | Max |', '| --- | --- | --- | --- | --- | --- |']
    for stage in STAGES + ['all four']:
        vals = [sum(r['stage_ms'].get(s, 0) for s in STAGES) if stage == 'all four' else r['stage_ms'].get(stage)
                for r in done]
        vals = [v for v in vals if v is not None]
        avg = sum(vals) / len(vals) if vals else None
        lines.append(f'| {stage} | {len(vals)} | {ms(avg)} | {ms(percentile(vals, 50))} | '
                     f'{ms(percentile(vals, 95))} | {ms(max(vals) if vals else None)} |')
    for group in ('pdf', 'scan'):
        vals = [r['stage_ms'].get('parse') for r in done if r['kind'] == group and 'parse' in r['stage_ms']]
        if vals:
            lines.append(f'| parse, {group} only | {len(vals)} | {ms(sum(vals) / len(vals))} | '
                         f'{ms(percentile(vals, 50))} | {ms(percentile(vals, 95))} | {ms(max(vals))} |')
    lines.append('')

    fresh = [r for r in done if r['file'] in new_names and r['end_to_end_s'] is not None]
    if fresh:
        e2e = [r['end_to_end_s'] for r in fresh]
        lines += ['## This run (files uploaded now)', '', '| Measure | Value |', '| --- | --- |',
                  f'| Files uploaded in this run | {len(fresh)} |',
                  f'| Upload to done, including queue wait | p50 {percentile(e2e, 50):.0f} s, '
                  f'p95 {percentile(e2e, 95):.0f} s, max {max(e2e):.0f} s |',
                  f'| Wall time until all finished | {waited / 60:.1f} min '
                  f'({len(fresh) / max(waited / 60, 0.1):.1f} files per min, 1 worker) |', '']

    lines += ['## Validation (needs_review on the AI version)', '', '| Measure | Value |', '| --- | --- |']
    planted = [r for r in done if r['planted']]
    clean = [r for r in done if not r['planted']]
    lines.append(f'| Planted-error invoices flagged | {pct(sum(bool(r["needs_review"]) for r in planted), len(planted))} |')
    no_dup = [r for r in clean if [c for c in r['issues'] if not c.startswith(('duplicate', 'possible_duplicate'))]]
    lines.append(f'| Clean invoices flagged | {pct(sum(bool(r["needs_review"]) for r in clean), len(clean))} |')
    lines.append(f'| Clean invoices flagged for a reason other than a duplicate | {pct(len(no_dup), len(clean))} |')
    lines.append('')
    codes = Counter(c for r in done for c in r['issues'])
    lines += ['Issue codes: ' + (', '.join(f'{c} {n}' for c, n in codes.most_common()) or 'none'), '']
    return '\n'.join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, help='only the first N invoices (2 files each)')
    ap.add_argument('--kind', choices=['pdf', 'scan', 'both'], default='both')
    ap.add_argument('--no-upload', action='store_true', help='score what is already in the database')
    ap.add_argument('--timeout', type=int, default=45, help='minutes to wait for the worker')
    args = ap.parse_args()

    todo = files_to_run(args.limit, args.kind)
    if not todo:
        sys.exit(f'no labelled files found in {DATA}')
    print(f'{len(todo)} files', file=sys.stderr)

    new_names: set[str] = set()
    if args.no_upload:
        with SessionLocal() as db:
            ids = {}
            for path, _, _ in todo:
                doc = db.scalar(select(Document).where(Document.filename == path.name)
                                .order_by(Document.created_at.desc()).limit(1))
                if doc:
                    ids[path.name] = doc.id
        waited = 0.0
    else:
        results = upload([p for p, _, _ in todo])
        ids = {name: r['id'] for name, r in results.items() if r.get('id')}
        new_names = {name for name, r in results.items() if r.get('id') and not r.get('already_uploaded')}
        rejected = {name: r.get('error_code') for name, r in results.items() if not r.get('id')}
        print(f'uploaded {len(new_names)} new, {len(ids) - len(new_names)} already there, '
              f'{len(rejected)} rejected {rejected or ""}', file=sys.stderr)
        waited = wait(list(ids.values()), args.timeout)

    with SessionLocal() as db:
        found = collect(db, ids)
    rows = []
    for path, label_path, kind in todo:
        if path.name not in found:
            continue
        r = found[path.name]
        label = json.loads(label_path.read_text(encoding='utf-8'))
        r.update(file=path.name, kind=kind, planted=label_path.stem in PLANTED_ERRORS)
        if r['data'] is not None:
            r['score'] = {**score_fields(r['data'], label), 'line_items': score_line_items(r['data'], label)}
        rows.append(r)
    print(report(rows, new_names, waited))


if __name__ == '__main__':
    main()