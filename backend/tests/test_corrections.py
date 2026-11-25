from datetime import date
from decimal import Decimal

import pytest

from app.services.corrections import CorrectionError, apply_corrections
from app.validation.labels import extraction_from_label
from app.validation.validate import validate_invoice

TODAY = date(2026, 11, 25)
LABEL = {
    'invoice_number': 'INV-1', 'invoice_date': '2026-03-14', 'supplier_name': 'ACME Ltd',
    'customer_name': 'Northwind', 'subtotal': '100.00', 'tax': '10.00', 'total': '120.00',
    'currency': 'USD', 'line_items': [],
}


def wrong_total():
    return extraction_from_label(LABEL)   # 100 + 10 is not 120


def test_wrong_total_is_flagged_before_correction():
    report = validate_invoice(wrong_total(), today=TODAY)
    assert 'total_mismatch' in [i.code for i in report.issues]


def test_correction_fixes_the_value_and_clears_the_issue():
    fixed, diff = apply_corrections(wrong_total(), {'total': '110.00'})
    assert fixed.total.value == Decimal('110.00')
    assert fixed.total.evidence == 'manual correction'
    assert diff == [{'field': 'total', 'old': '120.00', 'new': '110.00'}]
    report = validate_invoice(fixed, today=TODAY)
    assert 'total_mismatch' not in [i.code for i in report.issues]


def test_original_is_not_changed():
    inv = wrong_total()
    apply_corrections(inv, {'total': '110.00'})
    assert inv.total.value == Decimal('120.00')


def test_values_go_through_the_same_parsers():
    fixed, _ = apply_corrections(wrong_total(), {'currency': '€', 'invoice_date': '14/03/2026',
                                                 'tax': '1.234,50'})
    assert fixed.currency.value == 'EUR'
    assert fixed.invoice_date.value == date(2026, 3, 14)
    assert fixed.tax.value == Decimal('1234.50')


def test_empty_value_clears_the_field():
    fixed, diff = apply_corrections(wrong_total(), {'customer_name': ''})
    assert fixed.customer_name.value is None
    assert fixed.customer_name.status == 'missing'
    assert diff[0]['new'] is None


@pytest.mark.parametrize('changes, field', [
    ({'total': 'abc'}, 'total'),
    ({'invoice_date': 'someday'}, 'invoice_date'),
    ({'line_items': 'x'}, 'line_items'),
    ({'prompt_version': 'v9'}, 'prompt_version'),
])
def test_bad_corrections_are_refused(changes, field):
    with pytest.raises(CorrectionError) as err:
        apply_corrections(wrong_total(), changes)
    assert err.value.field == field