import csv
import io

import pandas as pd
from charset_normalizer import from_bytes

from app.pipeline.errors import CorruptFile
from app.schemas.parsed import PageResult

MAX_ROWS = 50_000


def _frame_to_text(df: pd.DataFrame) -> str:
    df = df.fillna('').astype(str)
    df = df.loc[~(df == '').all(axis=1)]   # drop fully empty rows
    lines = ('\t'.join(cell.strip() for cell in row) for row in df.itertuples(index=False, name=None))
    return '\n'.join(lines)


def _sheet_page(number: int, name: str | None, df: pd.DataFrame, warnings: list[str]) -> PageResult:
    if len(df) > MAX_ROWS:
        warnings.append(f'Sheet {name or number}: truncated to {MAX_ROWS} of {len(df)} rows')
        df = df.head(MAX_ROWS)
    return PageResult(page_number=number, text=_frame_to_text(df), method='table', sheet_name=name)


def parse_csv(data: bytes) -> tuple[list[PageResult], list[str]]:
    warnings: list[str] = []
    best = from_bytes(data, cp_isolation=['utf_8', 'cp1252']).best()
    if best is None:
        text = data.decode('utf-8', errors='replace')
        warnings.append('Encoding unknown; decoded as UTF-8 with replacement characters')
    else:
        text = str(best)
        if best.encoding not in ('ascii', 'utf_8'):
            warnings.append(f'Detected encoding: {best.encoding}')
    try:
        delimiter = csv.Sniffer().sniff(text[:4096], delimiters=',;\t|').delimiter
    except csv.Error:
        delimiter = ','
    try:
        df = pd.read_csv(io.StringIO(text), sep=delimiter, dtype=str, header=None,
                         keep_default_na=False, skip_blank_lines=True)
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise CorruptFile(f'Cannot parse CSV: {exc}') from exc
    return [_sheet_page(1, None, df, warnings)], warnings


def parse_excel(data: bytes, kind: str) -> tuple[list[PageResult], list[str]]:
    warnings: list[str] = []
    engine = 'openpyxl' if kind == 'xlsx' else 'xlrd'
    try:
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=str,
                               header=None, engine=engine)
    except Exception as exc:
        raise CorruptFile(f'Cannot read spreadsheet: {exc}') from exc
    pages = [_sheet_page(i, str(name), df, warnings) for i, (name, df) in enumerate(sheets.items(), start=1)]
    if not pages:
        raise CorruptFile('Spreadsheet has no sheets')
    if all(not p.text for p in pages):
        warnings.append('All sheets are empty (formulas without cached values read as empty)')
    return pages, warnings