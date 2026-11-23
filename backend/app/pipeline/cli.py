import argparse
from pathlib import Path

from app.pipeline.errors import DocumentError
from app.pipeline.parser import parse_document


def main() -> int:
    parser = argparse.ArgumentParser(description='Parse a document and print the result')
    parser.add_argument('path', type=Path)
    parser.add_argument('--json', action='store_true', help='print full JSON')
    args = parser.parse_args()

    try:
        result = parse_document(args.path.read_bytes(), args.path.name)
    except DocumentError as exc:
        print(f'ERROR [{exc.code}]: {exc.message}')
        return 1

    if args.json:
        print(result.model_dump_json(indent=2))
        return 0

    print(f'{result.filename}: {result.file_kind} ({result.mime_type}), '
          f'{result.page_count} page(s), {result.processing_ms} ms')
    for page in result.pages:
        conf = '' if page.ocr_confidence is None else f' conf={page.ocr_confidence}'
        label = f' [{page.sheet_name}]' if page.sheet_name else ''
        print(f'  page {page.page_number}{label}: {page.method}{conf}, {len(page.text)} chars')
    for warning in result.warnings:
        print(f'  WARNING: {warning}')
    print('--- first 400 characters ---')
    print(result.full_text()[:400])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())