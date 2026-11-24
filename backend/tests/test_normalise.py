from datetime import date
from decimal import Decimal

import pytest

from app.extraction.normalise import (
    date_is_ambiguous, parse_amount, parse_currency, parse_date,
)


@pytest.mark.parametrize('text, expected', [
    ('245.00', Decimal('245.00')),
    ('1,234.56', Decimal('1234.56')),
    ('1.234,56', Decimal('1234.56')),
    ('100,50', Decimal('100.50')),
    ('1,234', Decimal('1234')),
    ('$ 269.50', Decimal('269.50')),
    ('EUR 1.234.567,00', Decimal('1234567.00')),
    ('(12.50)', Decimal('-12.50')),
    ('', None),
    ('n/a', None),
])
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize('text, expected', [
    ('2025-03-14', date(2025, 3, 14)),
    ('14/03/2025', date(2025, 3, 14)),
    ('14.03.2025', date(2025, 3, 14)),
    ('March 14, 2025', date(2025, 3, 14)),
    ('14th Mar 2025', date(2025, 3, 14)),
    ('not a date', None),
])
def test_parse_date(text, expected):
    assert parse_date(text) == expected


def test_ambiguous_date_is_detected():
    assert date_is_ambiguous('03/04/2025')
    assert not date_is_ambiguous('14/03/2025')


@pytest.mark.parametrize('text, expected', [
    ('EUR', 'EUR'), ('usd', 'USD'), ('€', 'EUR'), ('US$', 'USD'),
    ('Tk', 'BDT'), ('৳', 'BDT'), ('', None), ('money', None),
])
def test_parse_currency(text, expected):
    assert parse_currency(text) == expected