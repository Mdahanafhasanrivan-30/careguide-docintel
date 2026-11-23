import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

import magic

from app.pipeline.errors import UnsupportedFileType

IMAGE_MIMES = {'image/png', 'image/jpeg', 'image/tiff', 'image/bmp', 'image/webp'}
XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
XLS_MIME = 'application/vnd.ms-excel'
OLE_MIMES = {XLS_MIME, 'application/CDFV2', 'application/x-ole-storage'}
ZIP_MIMES = {'application/zip', 'application/octet-stream', 'application/x-zip-compressed'}
TEXT_EXTS = {'.csv', '.tsv', '.txt'}


@dataclass(frozen=True)
class DetectedType:
    kind: str  # pdf | image | xlsx | xls | csv
    mime: str


def _is_xlsx(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return 'xl/workbook.xml' in zf.namelist()
    except zipfile.BadZipFile:
        return False


def detect_type(data: bytes, filename: str) -> DetectedType:
    # Content decides the type. The extension is only a tie-breaker.
    mime = magic.from_buffer(data[:8192], mime=True)
    ext = Path(filename).suffix.lower()

    if mime == 'application/pdf':
        return DetectedType('pdf', mime)
    if mime in IMAGE_MIMES:
        return DetectedType('image', mime)
    if mime == XLSX_MIME or (mime in ZIP_MIMES and _is_xlsx(data)):
        return DetectedType('xlsx', XLSX_MIME)
    if mime in OLE_MIMES and ext == '.xls':
        return DetectedType('xls', XLS_MIME)
    if ext in TEXT_EXTS and (mime.startswith('text/') or mime == 'application/csv'):
        return DetectedType('csv', mime)
    if ext in {'.csv', '.tsv'} and mime == 'application/octet-stream' and b'\x00' not in data[:8192]:
        return DetectedType('csv', 'text/csv')

    raise UnsupportedFileType(f'Unsupported file type: {mime} ({ext or "no extension"})')