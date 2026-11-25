import math
from datetime import date
from decimal import Decimal

from app.search.chunks import chunk_text, header_text
from app.search.embed import DIM, FakeEmbedder
from app.search.rank import rrf_merge


def test_short_text_is_one_chunk():
    assert chunk_text('Invoice INV-1 total 100.00') == ['Invoice INV-1 total 100.00']


def test_empty_text_has_no_chunks():
    assert chunk_text('   \n ') == []


def test_long_text_is_split_with_overlap():
    words = [f'w{n}' for n in range(400)]                 # about 1,900 characters
    chunks = chunk_text(' '.join(words), size=200, overlap=30)
    assert len(chunks) > 5
    assert all(len(c) <= 200 for c in chunks)
    first, second = chunks[0].split(), chunks[1].split()
    assert first[-1] in second and second[0] in first      # the next chunk repeats the last words
    assert set(' '.join(chunks).split()) == set(words)     # nothing is lost


def test_word_longer_than_a_chunk_is_kept():
    long = 'x' * 50
    assert chunk_text(f'a {long} b', size=20, overlap=5) == ['a', long, 'b']


def test_header_has_the_key_values():
    text = header_text('inv_003.pdf', 'INV-2025-1711', 'Padma Medical Supplies Ltd',
                       date(2025, 3, 14), Decimal('1084.02'), 'USD')
    assert text == ('Invoice INV-2025-1711 from Padma Medical Supplies Ltd dated 2025-03-14 '
                    'total 1084.02 USD. File inv_003.pdf.')


def test_header_skips_missing_values():
    assert header_text('scan.jpg', None, None, None, None, None) == 'Invoice. File scan.jpg.'


def test_fake_vectors_are_normalised_and_stable():
    a, b = FakeEmbedder().embed(['medical gloves box', 'medical gloves box'])
    assert len(a) == DIM and a == b
    assert math.isclose(sum(x * x for x in a), 1.0)


def test_fake_vectors_are_closer_for_shared_words():
    q, gloves, toner = FakeEmbedder().embed(['gloves', 'nitrile gloves box of 100', 'printer toner cartridge'])
    dot = lambda u, v: sum(x * y for x, y in zip(u, v))   # noqa: E731
    assert dot(q, gloves) > dot(q, toner)


def test_rrf_rewards_items_in_both_lists():
    merged = rrf_merge(['a', 'b', 'c'], ['c', 'd'])
    order = [item for item, _ in merged]
    assert order[0] == 'c'                    # in both lists beats first place in only one
    assert set(order) == {'a', 'b', 'c', 'd'}


def test_rrf_with_one_list_keeps_its_order():
    assert [i for i, _ in rrf_merge(['x', 'y', 'z'])] == ['x', 'y', 'z']