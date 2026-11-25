"""Manual corrections. Pure: no database. The API saves the result as a new version."""
from app.extraction.normalise import parse_amount, parse_currency, parse_date, parse_text
from app.schemas.invoice import DateField, InvoiceExtraction, MoneyField, TextField

# field name -> (field class, parser). The same parsers the AI path uses, so a
# corrected value is checked exactly like an extracted one.
EDITABLE = {
    'invoice_number': (TextField, parse_text),
    'invoice_date': (DateField, parse_date),
    'supplier_name': (TextField, parse_text),
    'customer_name': (TextField, parse_text),
    'subtotal': (MoneyField, parse_amount),
    'tax': (MoneyField, parse_amount),
    'total': (MoneyField, parse_amount),
    'currency': (TextField, parse_currency),
}


class CorrectionError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(f'{field}: {message}')
        self.field = field
        self.message = message


def _show(value) -> str | None:
    return None if value is None else str(value)


def apply_corrections(inv: InvoiceExtraction,
                      changes: dict[str, str | None]) -> tuple[InvoiceExtraction, list[dict]]:
    """Return a corrected copy and a list of {field, old, new}. "" or None clears a field."""
    updates, diff = {}, []
    for name, text in changes.items():
        if name not in EDITABLE:
            raise CorrectionError(name, 'this field cannot be corrected')
        cls, parse = EDITABLE[name]
        text = (text or '').strip()
        if not text:
            new = cls(status='missing')
        else:
            value = parse(text)
            if value is None:
                raise CorrectionError(name, f'could not read "{text}"')
            new = cls(value=value, raw=text, evidence='manual correction', confidence=1.0, status='ok')
        old = getattr(inv, name)
        updates[name] = new
        diff.append({'field': name, 'old': _show(old.value), 'new': _show(new.value)})
    return inv.model_copy(update=updates), diff