"""Decide what an adjustment row is (discount, charge, tax, rounding) and give its amount the right sign."""
import re
from decimal import Decimal

# Checked in this order: the first match wins.
KIND_WORDS = [
    ('payment', r'paid|payment|deposit|advance|balance|amount due|received'),
    ('rounding', r'round(ing|ed)?|round[- ]?off'),
    ('discount', r'discount|disc\.?|rebate|less|coupon|voucher|promo\w*|deduction'),
    ('tax', r'tax|vat|gst|cgst|sgst|igst|hst|pst|ait|duty'),
]


def adjustment_kind(label: str | None) -> str:
    """'Discount (5%)' -> 'discount', 'SGST 9%' -> 'tax', 'Advance paid' -> 'payment', else 'charge'."""
    text = (label or '').lower()
    for kind, words in KIND_WORDS:
        if re.search(rf'\b({words})\b', text):
            return kind
    return 'charge'                      # shipping, delivery, freight, handling, service fee ...


def signed_amount(kind: str, value: Decimal) -> Decimal:
    """Invoices print discounts as '-20.00', '(20.00)' or just '20.00'. Make the meaning explicit."""
    if kind == 'discount':
        return -abs(value)
    if kind in ('charge', 'tax'):
        return abs(value)
    return value                         # rounding keeps its printed sign: +0.40 or -0.76