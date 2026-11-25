"""Parse one file and extract invoice fields with the real LLM.

Run inside Docker:  dcrun python -m scripts.try_extract tests/fixtures/invoice_digital.pdf
"""
import argparse
from pathlib import Path

from app.extraction.errors import ExtractionError
from app.extraction.extract import extract_invoice
from app.extraction.llm import make_client
from app.pipeline.errors import DocumentError
from app.pipeline.parser import parse_document


def main() -> int:
    ap = argparse.ArgumentParser(description='Parse a file and extract invoice fields with the LLM')
    ap.add_argument('path', type=Path)
    args = ap.parse_args()
    try:
        doc = parse_document(args.path.read_bytes(), args.path.name)
        result = extract_invoice(doc.full_text(), make_client())
    except (DocumentError, ExtractionError) as exc:
        print(f'ERROR [{exc.code}]: {exc.message}')
        return 1
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())