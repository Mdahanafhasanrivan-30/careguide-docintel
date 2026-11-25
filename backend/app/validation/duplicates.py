"""Duplicate checks. Three levels, from sure to unsure:

1. duplicate_invoice  (error)   same supplier and same invoice number
2. duplicate_number   (warning) same invoice number, different supplier
3. possible_duplicate (warning) same supplier and either the same digits in the number
                                ('INV-2025-0456' vs '2025-0456') or the same date and total
"""
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.schemas.invoice import InvoiceExtraction
from app.schemas.validation import Issue

TOLERANCE = Decimal('0.01')
MIN_DIGITS = 3            # 'INV-1' vs 'PO-1' share one digit; that is not evidence of anything
IGNORED_WORDS = {'ltd', 'limited', 'inc', 'incorporated', 'llc', 'llp', 'plc', 'gmbh', 'co', 'company',
                 'corp', 'corporation', 'pvt', 'private', 'sa', 'ag', 'bv', 'the', 'and'}


def normalise_number(text: str | None) -> str | None:
    """'inv-2025 / 1711' and 'INV20251711' -> 'INV20251711'. Only letters and digits, upper case."""
    if not text:
        return None
    key = re.sub(r'[^A-Za-z0-9]', '', text).upper()
    return key or None


def number_digits(text: str | None) -> str | None:
    """'INV-2025-0456' and '2025/0456' -> '20250456'. None if too few digits to mean anything."""
    digits = re.sub(r'\D', '', text or '').lstrip('0')
    return digits if len(digits) >= MIN_DIGITS else None


def normalise_supplier(name: str | None) -> str | None:
    """'Café Müller GmbH' -> 'cafemuller'; 'PADMA MEDICAL SUPPLIES LIMITED' -> 'padmamedicalsupplies'."""
    if not name:
        return None
    text = unicodedata.normalize('NFKD', name)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch)).lower()   # é -> e
    words = [w for w in re.findall(r'[a-z0-9]+', text) if w not in IGNORED_WORDS]
    return ''.join(words) or None


@dataclass(frozen=True)
class SeenInvoice:
    """What we remember about an earlier invoice. Phase 4 builds these from database rows."""
    doc_id: str
    number: str | None
    number_key: str | None
    digits: str | None
    supplier_key: str | None
    invoice_date: date | None
    total: Decimal | None


def remember(doc_id: str, inv: InvoiceExtraction) -> SeenInvoice:
    number = inv.invoice_number.value
    return SeenInvoice(doc_id=doc_id, number=number, number_key=normalise_number(number),
                       digits=number_digits(number), supplier_key=normalise_supplier(inv.supplier_name.value),
                       invoice_date=inv.invoice_date.value, total=inv.total.value)


def _same_money(a: Decimal | None, b: Decimal | None) -> bool:
    return a is not None and b is not None and abs(a - b) <= TOLERANCE


def check_duplicates(inv: InvoiceExtraction, seen: list[SeenInvoice]) -> list[Issue]:
    me = remember('', inv)
    issues = []
    for other in seen:
        same_supplier = me.supplier_key is not None and me.supplier_key == other.supplier_key
        if me.number_key and me.number_key == other.number_key:
            if same_supplier:
                issues.append(Issue(code='duplicate_invoice', severity='error', field='invoice_number',
                                    message=f'same supplier and invoice number {me.number} as '
                                            f'{other.doc_id}; this invoice is probably entered twice'))
            else:
                issues.append(Issue(code='duplicate_number', severity='warning', field='invoice_number',
                                    message=f'invoice number {me.number} was already seen in '
                                            f'{other.doc_id} from another supplier; check it is not paid twice'))
        elif same_supplier and me.digits and me.digits == other.digits:
            issues.append(Issue(code='possible_duplicate', severity='warning', field='invoice_number',
                                message=f'invoice number {me.number} looks like {other.number} in '
                                        f'{other.doc_id} from the same supplier'))
        elif same_supplier and me.invoice_date and me.invoice_date == other.invoice_date \
                and _same_money(me.total, other.total):
            issues.append(Issue(code='possible_duplicate', severity='warning', field='invoice_number',
                                message=f'same supplier, date and total as {other.doc_id} '
                                        f'(number {other.number}); it may be the same invoice renumbered'))
    return issues