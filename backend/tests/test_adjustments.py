from decimal import Decimal

import pytest

from app.extraction.adjustments import adjustment_kind, signed_amount
from app.extraction.extract import extract_invoice
from app.extraction.llm import FakeLLMClient
from app.schemas.invoice import RawAdjustment, RawLineItem
from tests.test_extract import SOURCE, f, good_answer


@pytest.mark.parametrize('label, kind', [
    ('Discount (5%)', 'discount'), ('Less: trade discount', 'discount'), ('Coupon SAVE10', 'discount'),
    ('Shipping', 'charge'), ('Delivery charge', 'charge'), ('Service fee', 'charge'),
    ('SGST 9%', 'tax'), ('VAT 15%', 'tax'), ('AIT', 'tax'),
    ('Rounding', 'rounding'), ('Round off', 'rounding'),
    ('Advance paid', 'payment'), ('Balance due', 'payment'), ('Amount received', 'payment'),
    ('', 'charge'),
])
def test_adjustment_kind(label, kind):
    assert adjustment_kind(label) == kind


@pytest.mark.parametrize('kind, value, result', [
    ('discount', '20.00', '-20.00'), ('discount', '-20.00', '-20.00'),
    ('charge', '-15.00', '15.00'), ('tax', '22.05', '22.05'),
    ('rounding', '-0.76', '-0.76'), ('rounding', '0.40', '0.40'),
])
def test_signed_amount(kind, value, result):
    assert signed_amount(kind, Decimal(value)) == Decimal(result)


# ---- extraction of adjustments (FakeLLMClient, no network) --------------

ADJ_SOURCE = SOURCE.replace('Total Due EUR 269.50', 'Discount 20.00\nShipping 15.00\nAdvance paid 100.00\n'
                                                    'Total Due EUR 264.50')


def raw_adj(label, amount, evidence=None):
    return RawAdjustment(label=label, amount=amount, evidence=evidence or f'{label} {amount}')


def run(adjustments):
    fake = good_answer(total=f('264.50', 'Total Due EUR 264.50'),
                       currency=f('EUR', 'Total Due EUR 264.50'), adjustments=adjustments)
    return extract_invoice(ADJ_SOURCE, FakeLLMClient(fake))


def test_discount_printed_without_minus_becomes_negative():
    result = run([raw_adj('Discount', '20.00'), raw_adj('Shipping', '15.00')])
    assert [(a.kind, a.amount) for a in result.adjustments] == [
        ('discount', Decimal('-20.00')), ('charge', Decimal('15.00'))]
    assert result.warnings == []


def test_payment_row_is_ignored_with_warning():
    result = run([raw_adj('Advance paid', '100.00')])
    assert result.adjustments == []
    assert any('payment' in w for w in result.warnings)


def test_invented_adjustment_is_dropped():
    result = run([raw_adj('Handling', '9.99')])          # not in the document
    assert result.adjustments == []
    assert any('dropped' in w for w in result.warnings)


def test_unreadable_adjustment_is_kept_without_amount():
    source = ADJ_SOURCE + 'Insurance n/a\n'
    fake = good_answer(adjustments=[raw_adj('Insurance', 'n/a')])
    result = extract_invoice(source, FakeLLMClient(fake))
    assert result.adjustments[0].amount is None
    assert any('could not read' in w for w in result.warnings)


def test_old_answer_without_adjustments_still_works():
    result = extract_invoice(SOURCE, FakeLLMClient(good_answer()))   # model left the key out
    assert result.adjustments == []


@pytest.mark.parametrize('printed, amount, percent', [
    ('10%', None, '10'), ('5.00', '5.00', None), ('-5.00', '5.00', None), ('', None, None)])
def test_line_discount_is_read(printed, amount, percent):
    row = RawLineItem(description='Widget A', quantity='10', unit_price='12.50', amount='125.00',
                      discount=printed, evidence='Widget A 10 12.50 125.00')
    result = extract_invoice(SOURCE, FakeLLMClient(good_answer(line_items=[row])))
    line = result.line_items[0]
    assert line.discount == (None if amount is None else Decimal(amount))
    assert line.discount_percent == (None if percent is None else Decimal(percent))