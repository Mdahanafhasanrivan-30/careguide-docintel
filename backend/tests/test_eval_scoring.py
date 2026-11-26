from decimal import Decimal

import pytest

from app.evaluation.scoring import (FIELDS, norm_money, percentile, score_fields,
                                    score_line_items, truth)

LABEL = {
    'expected': {
        'invoice_number': 'INV-2025-7932', 'invoice_date': '2025-04-19',
        'supplier_name': 'Northwind Traders', 'customer_name': 'Dhaka Care Clinic',
        'subtotal': '1032.40', 'tax': '51.62', 'total': '1084.02', 'currency': 'EUR',
        'line_items': [{'amount': '105.40'}, {'amount': '411.00'}, {'amount': '516.00'}],
    },
    'printed': {'total': '1094.02'},
}


def field(value):
    return {'value': value, 'raw': str(value), 'evidence': '', 'confidence': 1.0, 'status': 'ok'}


def extraction(**changes):
    data = {f: field(v) for f, v in truth(LABEL).items()}
    data['line_items'] = [{'amount': field(a)} for a in ('516.00', '105.40', '411.00')]
    data.update(changes)
    return data


def test_perfect_extraction_scores_every_field():
    assert all(score_fields(extraction(), LABEL).values())
    assert set(score_fields(extraction(), LABEL)) == set(FIELDS)


def test_printed_value_is_the_truth_for_the_extractor():
    assert score_fields(extraction(total=field('1094.02')), LABEL)['total'] is True
    assert score_fields(extraction(total=field('1084.02')), LABEL)['total'] is False


def test_text_ignores_case_and_spaces_but_not_spelling():
    assert score_fields(extraction(supplier_name=field('northwind  TRADERS ')), LABEL)['supplier_name']
    assert not score_fields(extraction(supplier_name=field('Northwlnd Traders')), LABEL)['supplier_name']


def test_missing_on_both_sides_is_correct_and_one_side_is_wrong():
    label = {'expected': {**LABEL['expected'], 'customer_name': None}}
    assert score_fields(extraction(customer_name={'value': None, 'status': 'missing'}), label)['customer_name']
    assert not score_fields(extraction(), label)['customer_name']


@pytest.mark.parametrize('text, value', [
    ('1084.02', '1084.02'), ('1.094,02', '1094.02'), ('€ 1,094.02', '1094.02'),
    ('51,62', '51.62'), (1084.0, '1084.00'), ('', None), (None, None),
])
def test_money_forms(text, value):
    assert norm_money(text) == (None if value is None else Decimal(value))


def test_line_items_match_in_any_order_but_not_with_a_missing_row():
    assert score_line_items(extraction(), LABEL)
    assert not score_line_items(extraction(line_items=[{'amount': field('516.00')}]), LABEL)


def test_percentile_nearest_rank():
    times = [100, 200, 300, 400, 1000]
    assert percentile(times, 50) == 300
    assert percentile(times, 95) == 1000
    assert percentile([], 50) is None


def test_printed_text_that_is_not_a_value_falls_back_to_expected():
    label = {'expected': LABEL['expected'], 'printed': {'invoice_date': '19/04/2025', 'currency': None}}
    want = truth(label)
    assert want['invoice_date'] == '2025-04-19'
    assert want['currency'] is None            # not printed at all: the extractor should find nothing