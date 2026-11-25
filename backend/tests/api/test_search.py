"""Search against a real PostgreSQL (tsvector + pgvector). FakeEmbedder: no model, no network."""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.api.search import embedder_provider
from app.db.models import Document, DocumentChunk, ProcessingEvent
from app.extraction.llm import FakeLLMClient
from app.main import app
from app.search.embed import FakeEmbedder
from app.search.index import index_document
from app.services.processing import process_document
from tests.test_extract import SOURCE, good_answer

GLOVES = ('Padma Medical Supplies Ltd\nINVOICE INV-2025-0101\nNitrile examination gloves, box of 100\n'
          'Surgical masks 3-ply\nTotal BDT 12,450.00')
TONER = ('Dhaka Office Mart\nINVOICE OM-7781\nPrinter toner cartridge black\nA4 copy paper 80 gsm\n'
         'Total USD 310.50')


def add(db, name, text, supplier, number, total, currency, when, needs_review=False, index=True):
    doc = Document(filename=name, size_bytes=1, sha256=uuid.uuid4().hex * 2, storage_path='/x',
                   status='done', text=text, supplier_name=supplier, invoice_number=number,
                   total=Decimal(total), currency=currency, invoice_date=when, needs_review=needs_review)
    db.add(doc)
    db.flush()
    if index:
        index_document(db, doc, FakeEmbedder())
    db.commit()
    return doc.id


@pytest.fixture
def two_docs(db):
    gloves = add(db, 'gloves.pdf', GLOVES, 'Padma Medical Supplies Ltd', 'INV-2025-0101', '12450.00', 'BDT',
                 date(2025, 3, 1), needs_review=True)
    toner = add(db, 'toner.pdf', TONER, 'Dhaka Office Mart', 'OM-7781', '310.50', 'USD', date(2025, 6, 15))
    return gloves, toner


@pytest.fixture
def search(client):
    app.dependency_overrides[embedder_provider] = lambda: FakeEmbedder
    def run(**params):
        r = client.get('/api/v1/search', params=params)
        assert r.status_code == 200, r.text
        return r.json()
    return run


def names(body):
    return [h['document']['filename'] for h in body['hits']]


def test_keyword_finds_words_in_the_text(search, two_docs):
    body = search(q='toner', mode='keyword')
    assert names(body) == ['toner.pdf']
    assert '[toner]' in body['hits'][0]['snippet'].lower()


def test_keyword_uses_stemming(search, two_docs):
    assert names(search(q='glove', mode='keyword')) == ['gloves.pdf']      # "glove" matches "gloves"


def test_keyword_finds_supplier_and_number(search, two_docs):
    assert names(search(q='Padma', mode='keyword')) == ['gloves.pdf']
    assert names(search(q='OM-7781', mode='keyword')) == ['toner.pdf']


def test_keyword_handles_odd_input_safely(search, two_docs):
    for q in ['"unclosed', "'; DROP TABLE documents; --", 'gloves -masks', 'a & | !']:
        search(q=q, mode='keyword')                    # 200, never a 500
    assert names(search(q='toner', mode='keyword'))   # table still there


def test_semantic_finds_the_closest_document(search, two_docs):
    body = search(q='examination gloves', mode='semantic')
    assert names(body)[0] == 'gloves.pdf'
    assert 0 < body['hits'][0]['score'] <= 1


def test_hybrid_merges_both(search, two_docs):
    body = search(q='printer toner', mode='hybrid')
    assert body['mode'] == 'hybrid' and names(body)[0] == 'toner.pdf'


def test_filters_work_alone_and_with_a_query(search, two_docs):
    assert names(search(needs_review='true')) == ['gloves.pdf']
    assert names(search(currency='usd')) == ['toner.pdf']
    assert names(search(min_total='1000')) == ['gloves.pdf']
    assert names(search(date_from='2025-06-01', date_to='2025-06-30')) == ['toner.pdf']
    assert names(search(supplier='padma')) == ['gloves.pdf']
    assert names(search(supplier='100%')) == []                        # % is a literal, not a wildcard
    assert search(q='toner', mode='keyword', currency='BDT')['count'] == 0
    body = search()
    assert body['mode'] == 'filter' and names(body) == ['toner.pdf', 'gloves.pdf']   # newest date first


def test_correction_updates_keyword_search(client, search, db, two_docs):
    gloves, _ = two_docs
    doc = db.get(Document, gloves)
    doc.supplier_name = 'Renamed Traders'                              # what save_result does on a correction
    db.commit()
    assert names(search(q='Renamed', mode='keyword')) == ['gloves.pdf']   # generated column followed


def test_model_failure_gives_503_but_keyword_still_works(client, two_docs):
    def broken():
        raise RuntimeError('no model')
    app.dependency_overrides[embedder_provider] = lambda: broken
    assert client.get('/api/v1/search', params={'q': 'gloves', 'mode': 'semantic'}).status_code == 503
    assert client.get('/api/v1/search', params={'q': 'gloves', 'mode': 'keyword'}).status_code == 200


def test_worker_indexes_after_validation(db):
    doc = Document(filename='inv.pdf', size_bytes=1, sha256='c' * 64, storage_path='/x', status='queued', text=SOURCE)
    db.add(doc)
    db.commit()
    assert process_document(db, doc.id, lambda: FakeLLMClient(good_answer()), FakeEmbedder) == 'done'
    chunks = db.query(DocumentChunk).filter_by(document_id=doc.id).order_by(DocumentChunk.chunk_index).all()
    assert len(chunks) >= 2 and chunks[0].text.startswith('Invoice INV-2025-0042 from ACME')
    assert db.query(ProcessingEvent).filter_by(document_id=doc.id, stage='index', status='ok').count() == 1


def test_index_failure_keeps_the_document_done(db):
    doc = Document(filename='inv.pdf', size_bytes=1, sha256='d' * 64, storage_path='/x', status='queued', text=SOURCE)
    db.add(doc)
    db.commit()
    def broken():
        raise RuntimeError('model download failed')
    assert process_document(db, doc.id, lambda: FakeLLMClient(good_answer()), broken) == 'done'
    db.refresh(doc)
    assert doc.status == 'done' and doc.total == Decimal('269.50')
    assert db.query(ProcessingEvent).filter_by(document_id=doc.id, stage='index', status='failed').count() == 1


def test_reindex_replaces_old_chunks(db, two_docs):
    gloves, _ = two_docs
    doc = db.get(Document, gloves)
    first = db.query(DocumentChunk).filter_by(document_id=gloves).count()
    index_document(db, doc, FakeEmbedder())
    db.commit()
    assert db.query(DocumentChunk).filter_by(document_id=gloves).count() == first