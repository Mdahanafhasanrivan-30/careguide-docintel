"""Turn an eval_data label into an InvoiceExtraction. Used by tests and scripts only, never by the API."""
import json
from decimal import Decimal
from pathlib import Path

from app.extraction.adjustments import adjustment_kind
from app.extraction.normalise import parse_amount, parse_date, parse_text
from app.schemas.invoice import (
    Adjustment, DateField, InvoiceExtraction, LineItem, MoneyField, TextField,
)

FIELDS = {
    'invoice_number': (TextField, parse_text), 'invoice_date': (DateField, parse_date),
    'supplier_name': (TextField, parse_text), 'customer_name': (TextField, parse_text),
    'subtotal': (MoneyField, parse_amount), 'tax': (MoneyField, parse_amount),
    'total': (MoneyField, parse_amount), 'currency': (TextField, parse_text),
}


def extraction_from_label(expected: dict, printed: dict | None = None) -> InvoiceExtraction:
    """printed (optional) holds a field as printed when it differs from the clean value,
    e.g. {'currency': '$', 'invoice_date': '03/04/2025'}. It becomes the field's raw text."""
    printed = printed or {}
    fields = {}
    for name, (cls, parse) in FIELDS.items():
        value = expected.get(name)
        if value is None:
            fields[name] = cls(status='missing')
        else:
            raw = printed.get(name, value)
            fields[name] = cls(value=parse(value), raw=raw, evidence=raw, confidence=1.0, status='ok')
    items = []
    for i in expected.get('line_items', []):
        discount = i.get('discount', '')
        percent = discount.endswith('%')
        items.append(LineItem(description=i['description'], quantity=parse_amount(i['quantity']),
                              unit_price=parse_amount(i['unit_price']), amount=parse_amount(i['amount']),
                              discount=None if percent else parse_amount(discount),
                              discount_percent=parse_amount(discount) if percent else None))
    adjustments = [Adjustment(label=a['label'], kind=adjustment_kind(a['label']),
                              amount=Decimal(a['amount']), raw=a['amount'])
                   for a in expected.get('adjustments', [])]
    return InvoiceExtraction(**fields, line_items=items, adjustments=adjustments,
                             prompt_version='label', model='label', latency_ms=0)


def load_record(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def load_label(path: Path) -> InvoiceExtraction:
    record = load_record(path)
    return extraction_from_label(record['expected'], record.get('printed'))