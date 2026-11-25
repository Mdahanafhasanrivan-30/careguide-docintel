"""The 21 corner-case invoices from scripts/make_edge_cases.py, validated from their labels (no LLM)."""
from datetime import date
from pathlib import Path

import pytest

from app.validation.labels import load_label, load_record
from app.validation.validate import validate_batch

EVAL_EDGE = Path(__file__).resolve().parents[1] / 'eval_edge'
TODAY = date(2026, 11, 25)
PATHS = sorted(EVAL_EDGE.glob('e*.json'))

pytestmark = pytest.mark.skipif(not PATHS, reason='eval_edge not generated')


@pytest.fixture(scope='module')
def reports():
    return validate_batch([(p.stem, load_label(p)) for p in PATHS], today=TODAY)


@pytest.mark.parametrize('path', PATHS, ids=[p.stem for p in PATHS])
def test_edge_case_gives_expected_issues(path, reports):
    expected = load_record(path)['expected_issues']
    got = [issue.code for issue in reports[path.stem].issues]
    assert sorted(got) == sorted(expected)