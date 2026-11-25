"""Validate labels (no LLM, no cost) and print which invoices need review.

Run inside Docker:
  dcrun python -m scripts.validate_eval                    # the 30 Phase 2 invoices (eval_data)
  dcrun python -m scripts.validate_eval --data eval_edge   # the 21 corner cases
If a label has 'expected_issues', the script also says MATCH or DIFF for it.
"""
import argparse
from pathlib import Path

from app.validation.labels import load_label, load_record
from app.validation.validate import validate_batch

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description='Validate labeled invoices')
    ap.add_argument('--data', default='eval_data', help='folder under backend/ with *.json labels')
    args = ap.parse_args()
    folder = ROOT / args.data
    paths = sorted(p for p in folder.glob('*.json'))
    if not paths:
        print(f'No labels in {folder}; run scripts.make_dataset or scripts.make_edge_cases first')
        return 1
    reports = validate_batch([(p.stem, load_label(p)) for p in paths])
    flagged, diffs = [], []
    for path in paths:
        record, report = load_record(path), reports[path.stem]
        got = [issue.code for issue in report.issues]
        status = 'REVIEW' if report.needs_review else 'ok    '
        check = ''
        if 'expected_issues' in record:
            ok = sorted(got) == sorted(record['expected_issues'])
            check = 'MATCH' if ok else f'DIFF (expected {record["expected_issues"]})'
            if not ok:
                diffs.append(path.stem)
        print(f'{path.stem:28} {status}  {check}  (planted: {record.get("edge_case") or "-"})')
        for issue in report.issues:
            print(f'    [{issue.severity}] {issue.code}: {issue.message}')
        if report.needs_review:
            flagged.append(path.stem)
    print(f'\n{len(flagged)} of {len(paths)} need review: {", ".join(flagged)}')
    if diffs:
        print(f'DIFF on {len(diffs)}: {", ".join(diffs)}')
    return 1 if diffs else 0


if __name__ == '__main__':
    raise SystemExit(main())