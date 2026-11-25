"""Run parse_document + extract_invoice on the labeled dataset and print field accuracy.

Run inside Docker:  dcrun python -m scripts.eval_extraction --limit 5
Costs real API calls (2 per invoice: the PDF and the scan). Start with --limit 5.
"""
import argparse
import json
import re
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

from app.extraction.errors import ExtractionError
from app.extraction.extract import extract_invoice
from app.extraction.llm import make_client
from app.pipeline.errors import DocumentError
from app.pipeline.parser import parse_document

DATA = Path(__file__).resolve().parents[1] / 'eval_data'
FIELDS = ['invoice_number', 'invoice_date', 'supplier_name', 'customer_name',
          'subtotal', 'tax', 'total', 'currency']
MONEY = {'subtotal', 'tax', 'total'}


def same(field: str, expected, got) -> bool:
    if expected is None or got is None:
        return expected is None and got is None      # null must stay null: no inventing
    if field in MONEY:
        return Decimal(expected) == got
    if field == 'invoice_date':
        return expected == got.isoformat()
    return re.sub(r'\s+', ' ', expected).strip().lower() == re.sub(r'\s+', ' ', got).strip().lower()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=5, help='number of invoices (0 = all)')
    ap.add_argument('--kind', choices=['pdf', 'scan', 'both'], default='both')
    args = ap.parse_args()

    labels = sorted(DATA.glob('inv_*.json'))
    if args.limit:
        labels = labels[:args.limit]
    client = make_client()
    correct, total, failures, latencies, tokens = Counter(), 0, [], [], 0
    rows = []

    for label_path in labels:
        record = json.loads(label_path.read_text(encoding='utf-8'))
        files = record['files'] if args.kind == 'both' else [
            f for f in record['files'] if (f.endswith('.pdf')) == (args.kind == 'pdf')]
        for name in files:
            started = time.perf_counter()
            try:
                doc = parse_document((DATA / name).read_bytes(), name)
                result = extract_invoice(doc.full_text(), client)
            except (DocumentError, ExtractionError) as exc:
                failures.append(f'{name}: {exc}')
                continue
            latencies.append(time.perf_counter() - started)
            tokens += result.input_tokens + result.output_tokens
            total += 1
            wrong = []
            for field in FIELDS:
                if same(field, record['expected'][field], getattr(result, field).value):
                    correct[field] += 1
                else:
                    wrong.append(field)
            rows.append((name, record['edge_case'] or '-', ', '.join(wrong) or 'all correct'))

    print(f'{"file":22} {"edge case":18} result')
    for row in rows:
        print(f'{row[0]:22} {row[1]:18} {row[2]}')
    print(f'\nDocuments extracted: {total}, failed: {len(failures)}')
    for failure in failures:
        print('  FAILED', failure)
    if total:
        print('\nField accuracy:')
        for field in FIELDS:
            print(f'  {field:16} {correct[field] / total:6.1%}')
        print(f'\nAverage seconds per document: {sum(latencies) / len(latencies):.1f}')
        print(f'Total tokens: {tokens}')


if __name__ == '__main__':
    main()