"""Parse, extract (real LLM) and validate several files as one batch.

Run inside Docker:
  dcrun python -m scripts.try_validate eval_data/inv_003.pdf eval_data/inv_005.pdf \
      eval_data/inv_009.pdf eval_data/inv_021.pdf
  dcrun sh -c 'python -m scripts.try_validate eval_edge/*.pdf'
  dcrun sh -c 'python -m scripts.try_validate eval_edge/*_scan.jpg'   (after make_edge_cases --scans)
  dcrun sh -c 'python -m scripts.try_validate my_docs/*'              (labels *.json are skipped)
(sh -c makes the * expand inside the container, where the files are.)
Each file is one Gemini request. Files are checked in the order given (duplicates look backwards).
If a JSON label with 'expected_issues' sits next to a file, the script says MATCH or DIFF.
"""
import argparse
import json
from pathlib import Path

from app.extraction.errors import ExtractionError
from app.extraction.extract import extract_invoice
from app.extraction.llm import make_client
from app.pipeline.errors import DocumentError
from app.pipeline.parser import parse_document
from app.validation.validate import validate_batch


def expected_issues(path: Path) -> list[str] | None:
    label = path.with_name(path.stem.removesuffix('_scan') + '.json')   # e01_discount_scan.jpg -> e01_discount.json
    if not label.exists():
        return None
    return json.loads(label.read_text(encoding='utf-8')).get('expected_issues')


def main() -> int:
    ap = argparse.ArgumentParser(description='Extract and validate files as one batch')
    ap.add_argument('paths', type=Path, nargs='+')
    args = ap.parse_args()
    client = make_client()
    invoices = []
    for path in args.paths:
        if path.suffix == '.json':
            continue                    # a label, not a document
        if not path.is_file():
            print(f'{path}  ERROR: file not found')
            continue
        try:
            doc = parse_document(path.read_bytes(), path.name)
            invoices.append((path.name, extract_invoice(doc.full_text(), client)))
        except (DocumentError, ExtractionError) as exc:
            print(f'{path.name}  ERROR [{exc.code}]: {exc.message}')
    reports = validate_batch(invoices)
    paths = {p.name: p for p in args.paths}
    diffs = []
    for name, inv in invoices:
        report = reports[name]
        got = [issue.code for issue in report.issues]
        want = expected_issues(paths[name])
        check = ''
        if want is not None:
            check = 'MATCH' if sorted(got) == sorted(want) else f'DIFF (expected {want})'
            if check != 'MATCH':
                diffs.append(name)
        print(f'{name}  total={inv.total.value}  needs_review={report.needs_review}  {check}')
        for issue in report.issues:
            print(f'    [{issue.severity}] {issue.code}: {issue.message}')
        for warning in inv.warnings:
            print(f'    (extraction) {warning}')
    if diffs:
        print(f'\nDIFF on {len(diffs)} of {len(invoices)}: {", ".join(diffs)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())