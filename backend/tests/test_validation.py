from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.schemas.invoice import (
    Adjustment, DateField, InvoiceExtraction, LineItem, MoneyField, TextField,
)
from app.validation.duplicates import normalise_number, normalise_supplier, number_digits
from app.validation.labels import load_label
from app.validation.validate import validate_batch, validate_invoice

EVAL_DATA = Path(__file__).resolve().parents[1] / 'eval_data'
TODAY = date(2026, 11, 25)          # fixed, so the date tests never go stale


def text(value, confidence=0.9, raw=None):
    return TextField(value=value, raw=raw or value, evidence=raw or value, confidence=confidence, status='ok')


def money(value):
    return MoneyField(value=Decimal(value), raw=value, evidence=value, confidence=0.9, status='ok')


def day(d: date, raw=None):
    raw = raw or d.isoformat()
    return DateField(value=d, raw=raw, evidence=raw, confidence=0.9, status='ok')


def item(qty, unit, amount, description='Widget', discount=None, percent=None):
    def dec(v):
        return None if v is None else Decimal(v)
    return LineItem(description=description, quantity=dec(qty), unit_price=dec(unit), amount=dec(amount),
                    discount=dec(discount), discount_percent=dec(percent))


def adj(label, kind, amount):
    return Adjustment(label=label, kind=kind, amount=None if amount is None else Decimal(amount), raw=amount)


def good_invoice(**changes) -> InvoiceExtraction:
    data = dict(
        invoice_number=text('INV-2025-0042'),
        invoice_date=day(date(2025, 3, 14), '14/03/2025'),
        supplier_name=text('ACME Supplies Ltd'),
        customer_name=text('Northwind Traders'),
        subtotal=money('245.00'), tax=money('24.50'), total=money('269.50'),
        currency=text('EUR'),
        line_items=[item('10', '12.50', '125.00'), item('4', '30.00', '120.00')],
        prompt_version='test', model='fake', latency_ms=0,
    )
    data.update(changes)
    return InvoiceExtraction(**data)


def codes(report):
    return [issue.code for issue in report.issues]


def check(inv, seen=None):
    return validate_invoice(inv, seen, today=TODAY)


# ---- basic rules --------------------------------------------------------

def test_clean_invoice_needs_no_review():
    report = check(good_invoice())
    assert report.issues == []
    assert report.needs_review is False
    assert report.review_reasons == []


def test_wrong_total_is_an_error():
    report = check(good_invoice(total=money('279.50')))
    issue = report.issues[0]
    assert issue.code == 'total_mismatch' and issue.severity == 'error'
    assert issue.expected == Decimal('269.50') and issue.found == Decimal('279.50')
    assert report.needs_review is True


def test_one_cent_rounding_is_allowed():
    assert 'total_mismatch' not in codes(check(good_invoice(total=money('269.51'))))


def test_missing_tax_counts_as_zero():
    inv = good_invoice(tax=MoneyField(status='missing'), total=money('245.00'))
    assert codes(check(inv)) == ['tax_missing']


def test_unreadable_tax_does_not_guess_zero():
    inv = good_invoice(tax=MoneyField(raw='n/a', status='unparseable'))
    assert codes(check(inv)) == ['tax_unparseable']


def test_missing_required_field_is_an_error():
    report = check(good_invoice(invoice_number=TextField(status='missing')))
    assert report.issues[0].code == 'invoice_number_missing'
    assert report.issues[0].severity == 'error'


def test_no_evidence_field_is_flagged():
    inv = good_invoice(supplier_name=TextField(raw='ACME Ltd', status='no_evidence'))
    assert 'supplier_name_no_evidence' in codes(check(inv))


def test_low_confidence_is_a_warning():
    assert codes(check(good_invoice(supplier_name=text('ACME Supplies Ltd', confidence=0.3)))) == ['low_confidence']


def test_ambiguous_date_is_a_warning():
    inv = good_invoice(invoice_date=day(date(2025, 4, 3), '03/04/2025'))
    assert codes(check(inv)) == ['ambiguous_date']


# ---- line items ---------------------------------------------------------

def test_line_amount_must_equal_quantity_times_price():
    items = [item('10', '12.50', '125.00'), item('4', '30.00', '130.00')]
    inv = good_invoice(line_items=items, subtotal=money('255.00'), total=money('279.50'))
    assert codes(check(inv)) == ['line_amount_mismatch']


def test_line_items_must_add_up_to_subtotal():
    assert codes(check(good_invoice(line_items=[item('10', '12.50', '125.00')]))) == ['line_items_sum_mismatch']


def test_no_line_items_is_a_warning():
    assert codes(check(good_invoice(line_items=[]))) == ['no_line_items']


def test_flat_fee_row_is_fine():
    items = [item('10', '12.50', '125.00'), item(None, None, '120.00', 'Delivery fee')]
    assert check(good_invoice(line_items=items)).issues == []


def test_row_with_only_quantity_is_incomplete():
    items = [item('10', '12.50', '125.00'), item('4', None, '120.00')]
    assert codes(check(good_invoice(line_items=items))) == ['line_item_incomplete']


def test_row_without_amount_is_incomplete():
    items = [item('10', '12.50', '125.00'), item('4', '30.00', None)]
    assert codes(check(good_invoice(line_items=items))) == ['line_item_incomplete']


def test_line_discount_percent_is_applied():
    items = [item('10', '12.50', '112.50', percent='10'), item('4', '30.00', '120.00')]
    inv = good_invoice(line_items=items, subtotal=money('232.50'), tax=money('23.25'), total=money('255.75'))
    assert check(inv).issues == []


def test_line_discount_amount_is_applied():
    items = [item('10', '12.50', '120.00', discount='5.00'), item('4', '30.00', '120.00')]
    inv = good_invoice(line_items=items, subtotal=money('240.00'), tax=money('24.00'), total=money('264.00'))
    assert check(inv).issues == []


def test_wrong_amount_after_line_discount_is_caught():
    items = [item('10', '12.50', '115.00', percent='10'), item('4', '30.00', '120.00')]
    inv = good_invoice(line_items=items, subtotal=money('235.00'), tax=money('23.50'), total=money('258.50'))
    report = check(inv)
    assert codes(report) == ['line_amount_mismatch']
    assert '- 10%' in report.issues[0].message


# ---- adjustments: discount, shipping, extra tax, rounding ---------------

def test_discount_is_subtracted():
    inv = good_invoice(adjustments=[adj('Discount', 'discount', '-20.00')], total=money('249.50'))
    assert check(inv).issues == []


def test_shipping_and_second_tax_are_added():
    inv = good_invoice(adjustments=[adj('Shipping', 'charge', '15.00'), adj('SGST 9%', 'tax', '22.05')],
                       total=money('306.55'))
    assert check(inv).issues == []


def test_rounding_line_is_added_with_its_sign():
    inv = good_invoice(adjustments=[adj('Rounding', 'rounding', '0.50')], total=money('270.00'))
    assert check(inv).issues == []


def test_forgotten_discount_gives_mismatch():
    report = check(good_invoice(total=money('249.50')))   # discount row was not extracted
    assert codes(report) == ['total_mismatch']


def test_unreadable_adjustment_skips_total_check():
    inv = good_invoice(adjustments=[adj('Discount', 'discount', None)], total=money('249.50'))
    assert codes(check(inv)) == ['adjustment_unreadable']


def test_large_rounding_is_a_warning():
    inv = good_invoice(adjustments=[adj('Rounding', 'rounding', '-9.50')], total=money('260.00'))
    assert codes(check(inv)) == ['large_rounding']


def test_tax_included_in_prices_is_a_warning_not_an_error():
    inv = good_invoice(total=money('245.00'))             # 245.00 already includes 24.50 VAT
    report = check(inv)
    assert codes(report) == ['tax_included']
    assert report.issues[0].severity == 'warning'


# ---- missing subtotal ---------------------------------------------------

def test_missing_subtotal_uses_line_sum():
    inv = good_invoice(subtotal=MoneyField(status='missing'))
    assert codes(check(inv)) == ['subtotal_missing']      # 245 + 24.50 = 269.50 still checked


def test_missing_subtotal_still_catches_wrong_total():
    report = check(good_invoice(subtotal=MoneyField(status='missing'), total=money('300.00')))
    assert codes(report) == ['subtotal_missing', 'total_mismatch']
    assert report.issues[1].message.startswith('line items + tax')


def test_unreadable_subtotal_skips_total_check():
    inv = good_invoice(subtotal=MoneyField(raw='??', status='unparseable'), total=money('300.00'))
    assert codes(check(inv)) == ['subtotal_unparseable']


# ---- signs --------------------------------------------------------------

def test_credit_note_gives_one_warning():
    inv = good_invoice(subtotal=money('-245.00'), tax=money('-24.50'), total=money('-269.50'),
                       line_items=[item('-10', '12.50', '-125.00'), item('-4', '30.00', '-120.00')])
    report = check(inv)
    assert codes(report) == ['negative_total']
    assert report.issues[0].severity == 'warning'


def test_zero_total_is_a_warning():
    inv = good_invoice(subtotal=money('0.00'), tax=money('0.00'), total=money('0.00'),
                       line_items=[item('1', '0.00', '0.00')])
    assert codes(check(inv)) == ['zero_total']


def test_negative_line_on_normal_invoice_is_flagged():
    items = [item('10', '12.50', '125.00'), item('4', '30.00', '120.00'), item('-1', '10.00', '-10.00')]
    inv = good_invoice(line_items=items, subtotal=money('235.00'), total=money('259.50'))
    assert codes(check(inv)) == ['negative_line']


def test_discount_row_in_table_is_not_flagged():
    items = [item('10', '12.50', '125.00'), item('4', '30.00', '120.00'),
             item(None, None, '-20.00', 'Loyalty discount')]
    inv = good_invoice(line_items=items, subtotal=money('225.00'), total=money('249.50'))
    assert check(inv).issues == []


def test_negative_tax_on_positive_invoice_is_flagged():
    inv = good_invoice(tax=money('-24.50'), total=money('220.50'))
    assert codes(check(inv)) == ['negative_amount']


# ---- dates --------------------------------------------------------------

def test_future_date_is_an_error():
    report = check(good_invoice(invoice_date=day(date(2027, 1, 10))))
    assert codes(report) == ['future_date']
    assert report.issues[0].severity == 'error'


def test_tomorrow_is_allowed_for_time_zones():
    assert check(good_invoice(invoice_date=day(date(2026, 11, 26)))).issues == []


def test_very_old_date_is_a_warning():
    assert codes(check(good_invoice(invoice_date=day(date(2019, 1, 15))))) == ['old_date']


# ---- currency -----------------------------------------------------------

def test_unknown_currency_is_an_error():
    report = check(good_invoice(currency=text('XYZ')))
    assert codes(report) == ['currency_unknown']
    assert report.issues[0].severity == 'error'


def test_dollar_sign_alone_is_a_warning():
    assert codes(check(good_invoice(currency=text('USD', raw='$')))) == ['currency_assumed']


@pytest.mark.parametrize('printed, code', [('USD', 'USD'), ('US$', 'USD'), ('Tk', 'BDT'), ('€', 'EUR')])
def test_clear_currency_is_fine(printed, code):
    assert check(good_invoice(currency=text(code, raw=printed))).issues == []


# ---- duplicates ---------------------------------------------------------

@pytest.mark.parametrize('raw', ['INV-2025-0042', 'inv 2025/0042', ' INV_2025_0042 '])
def test_invoice_numbers_normalise_to_one_key(raw):
    assert normalise_number(raw) == 'INV20250042'


@pytest.mark.parametrize('name', ['ACME Supplies Ltd', 'ACME SUPPLIES LIMITED', 'Acme Supplies Ltd.',
                                  'The ACME Supplies Co.'])
def test_supplier_names_normalise_to_one_key(name):
    assert normalise_supplier(name) == 'acmesupplies'


def test_accents_are_ignored_in_supplier_names():
    assert normalise_supplier('Café Müller GmbH') == normalise_supplier('Cafe Muller')


def test_number_digits():
    assert number_digits('INV-2025-0456') == number_digits('2025/0456') == '20250456'
    assert number_digits('A-7') is None                    # too short to mean anything


def batch(*invoices):
    return validate_batch([(f'doc_{i}', inv) for i, inv in enumerate(invoices)], today=TODAY)


def test_same_supplier_same_number_is_a_duplicate_invoice():
    reports = batch(good_invoice(), good_invoice(invoice_number=text('inv-2025-0042')))
    assert reports['doc_0'].needs_review is False
    assert codes(reports['doc_1']) == ['duplicate_invoice']
    assert reports['doc_1'].issues[0].severity == 'error'
    assert 'doc_0' in reports['doc_1'].review_reasons[0]


def test_other_supplier_same_number_is_a_warning():
    reports = batch(good_invoice(), good_invoice(supplier_name=text('Northwind Traders')))
    assert codes(reports['doc_1']) == ['duplicate_number']
    assert reports['doc_1'].issues[0].severity == 'warning'


def test_number_with_prefix_dropped_is_possible_duplicate():
    reports = batch(good_invoice(), good_invoice(invoice_number=text('2025-0042'), total=money('100.00'),
                                                 tax=MoneyField(status='missing'),
                                                 subtotal=money('100.00'),
                                                 line_items=[item('1', '100.00', '100.00')]))
    assert codes(reports['doc_1']) == ['tax_missing', 'possible_duplicate']


def test_renumbered_invoice_with_same_date_and_total_is_possible_duplicate():
    reports = batch(good_invoice(), good_invoice(invoice_number=text('B-9911')))
    assert codes(reports['doc_1']) == ['possible_duplicate']


def test_other_supplier_same_date_and_total_is_not_a_duplicate():
    reports = batch(good_invoice(), good_invoice(invoice_number=text('B-9911'),
                                                 supplier_name=text('Northwind Traders')))
    assert reports['doc_1'].issues == []


# ---- the planted edge cases from eval_data ------------------------------

needs_data = pytest.mark.skipif(not (EVAL_DATA / 'inv_021.json').exists(),
                                reason='eval_data not generated')


def label(n: int) -> InvoiceExtraction:
    return load_label(EVAL_DATA / f'inv_{n:03d}.json')


@needs_data
def test_inv_005_missing_tax():
    assert codes(check(label(5))) == ['tax_missing']


@needs_data
def test_inv_009_wrong_total():
    report = check(label(9))
    assert codes(report) == ['total_mismatch']
    issue = report.issues[0]
    assert issue.found == Decimal('1094.02')
    assert issue.expected == Decimal('1084.02')
    assert issue.found - issue.expected == Decimal('10.00')


@needs_data
def test_inv_021_duplicate_of_inv_003():
    reports = validate_batch([('inv_003', label(3)), ('inv_021', label(21))], today=TODAY)
    assert reports['inv_003'].needs_review is False
    assert codes(reports['inv_021']) == ['duplicate_number']       # different supplier
    assert 'inv_003' in reports['inv_021'].review_reasons[0]


@needs_data
def test_only_planted_cases_are_flagged():
    reports = validate_batch([(f'inv_{n:03d}', label(n)) for n in range(1, 31)], today=TODAY)
    flagged = sorted(doc for doc, report in reports.items() if report.needs_review)
    assert flagged == ['inv_005', 'inv_009', 'inv_013', 'inv_017', 'inv_021']