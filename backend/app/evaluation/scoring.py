"""Scoring for the end-to-end evaluation. Pure: no database, no network, so it is unit-tested.

A label file looks like {"expected": {...}, "printed": {...}}. "expected" holds the correct
values; "printed" holds values that are printed wrongly on purpose (inv_009 prints total
1094.02 although the right total is 1084.02). The extractor's job is to read the page, so it is
scored against the printed value when there is one. Catching the wrong total is the validator's
job, and that is scored separately (planted errors).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

FIELDS = ['invoice_number', 'invoice_date', 'supplier_name', 'customer_name',
          'subtotal', 'tax', 'total', 'currency']
MONEY = {'subtotal', 'tax', 'total'}
CENT = Decimal('0.01')


def value_of(x):
    """Extraction fields are stored as {value, raw, evidence, confidence, status}; labels are plain."""
    if isinstance(x, dict):
        return x.get('value')
    return x


def _empty(x) -> bool:
    return x is None or (isinstance(x, str) and not x.strip())


def norm_money(x) -> Decimal | None:
    if _empty(x):
        return None
    text = str(x).strip()
    try:
        return Decimal(text).quantize(CENT)
    except InvalidOperation:
        pass
    # printed values can look like '1.094,02' or '€ 1,094.02': keep digits, signs and separators
    text = re.sub(r'[^0-9,.\-]', '', text)
    if ',' in text and '.' in text:
        if text.rfind(',') > text.rfind('.'):       # 1.094,02 -> European
            text = text.replace('.', '').replace(',', '.')
        else:                                         # 1,094.02
            text = text.replace(',', '')
    elif ',' in text:
        head, _, tail = text.rpartition(',')
        text = f'{head.replace(",", "")}.{tail}' if len(tail) == 2 else text.replace(',', '')
    try:
        return Decimal(text).quantize(CENT)
    except InvalidOperation:
        return None


def norm_date(x) -> date | None:
    if _empty(x):
        return None
    try:
        return date.fromisoformat(str(x).strip()[:10])
    except ValueError:
        return None


def norm_text(x) -> str | None:
    if _empty(x):
        return None
    text = unicodedata.normalize('NFKC', str(x)).casefold()
    return re.sub(r'\s+', ' ', text).strip()


def norm(field: str, x):
    x = value_of(x)
    if field in MONEY:
        return norm_money(x)
    if field == 'invoice_date':
        return norm_date(x)
    if field == 'currency':
        return None if _empty(x) else str(x).strip().upper()
    return norm_text(x)


def truth(label: dict) -> dict:
    """The values the extractor should read. A printed value overrides the expected one when it
    is empty (not printed at all) or can be read as a value (1094.02, 1.094,02). Printed text that
    is only a different way of writing the same value (a date like 19/04/2025) falls back to expected."""
    expected = label.get('expected', label)
    printed = label.get('printed') or {}
    out = {}
    for f in FIELDS:
        if f in printed and (_empty(printed[f]) or norm(f, printed[f]) is not None):
            out[f] = printed[f]
        else:
            out[f] = expected.get(f)
    return out


def score_fields(extracted: dict, label: dict) -> dict[str, bool]:
    """field -> correct? Missing on both sides counts as correct (the field is really absent)."""
    want = truth(label)
    return {f: norm(f, extracted.get(f)) == norm(f, want[f]) for f in FIELDS}


def _amounts(items) -> list[Decimal | None]:
    out = []
    for item in items or []:
        amount = item.get('amount') if isinstance(item, dict) else None
        out.append(norm_money(value_of(amount)))
    return sorted(out, key=lambda d: (d is None, d or 0))


def score_line_items(extracted: dict, label: dict) -> bool:
    """Same number of rows and the same row amounts (order ignored)."""
    expected = label.get('expected', label)
    return _amounts(extracted.get('line_items')) == _amounts(expected.get('line_items'))


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile: p50 is the median, p95 is the value 95% of runs stay under."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * p // 100))        # ceil(n * p / 100)
    return ordered[int(rank) - 1]


def pct(part: int, whole: int) -> str:
    return '-' if whole == 0 else f'{100 * part / whole:.1f}% ({part}/{whole})'