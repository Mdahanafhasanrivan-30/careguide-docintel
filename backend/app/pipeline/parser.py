import time
from pathlib import Path

from app.pipeline.detect import detect_type
from app.pipeline.errors import CorruptFile, FileTooLarge
from app.pipeline.images import parse_image
from app.pipeline.pdf import parse_pdf
from app.pipeline.sheets import parse_csv, parse_excel
from app.schemas.parsed import ParsedDocument

MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


def parse_document(data: bytes, filename: str) -> ParsedDocument:
    started = time.perf_counter()
    if not data:
        raise CorruptFile('File is empty')
    if len(data) > MAX_FILE_BYTES:
        raise FileTooLarge(f'File is {len(data)} bytes (limit {MAX_FILE_BYTES})')

    detected = detect_type(data, filename)
    if detected.kind == 'pdf':
        pages, warnings = parse_pdf(data)
    elif detected.kind == 'image':
        pages, warnings = parse_image(data)
    elif detected.kind == 'csv':
        pages, warnings = parse_csv(data)
    else:  # xlsx / xls
        pages, warnings = parse_excel(data, detected.kind)

    return ParsedDocument(
        filename=Path(filename).name,   # never trust a client path
        mime_type=detected.mime,
        file_kind=detected.kind,
        page_count=len(pages),
        pages=pages,
        warnings=warnings,
        processing_ms=round((time.perf_counter() - started) * 1000),
    )