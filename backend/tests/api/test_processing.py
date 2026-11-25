"""The worker pipeline against a real PostgreSQL, with FakeLLMClient (no network)."""
import uuid
from decimal import Decimal

import pytest

from app.db.models import Document, Extraction, ProcessingEvent
from app.extraction.errors import LLMUnavailable
from app.extraction.llm import FakeLLMClient
from app.services.processing import process_document, wait_for_retry
from tests.test_extract import SOURCE, good_answer


def fake():
    return FakeLLMClient(good_answer())


def busy():
    class Busy:
        model = 'busy'

        def extract(self, system, user):
            raise LLMUnavailable('LLM busy after 4 tries: 503 overloaded')
    return Busy()


def add_doc(db, text=SOURCE, path='/nowhere', name='inv.pdf') -> uuid.UUID:
    doc = Document(filename=name, size_bytes=1, sha256=uuid.uuid4().hex * 2, storage_path=path,
                   status='queued', text=text)
    db.add(doc)
    db.commit()
    return doc.id


def stages(db, doc_id):
    return [(e.stage, e.status) for e in db.query(ProcessingEvent)
            .filter_by(document_id=doc_id).order_by(ProcessingEvent.id)]


def test_happy_path_saves_values_and_history(db):
    doc_id = add_doc(db)
    assert process_document(db, doc_id, fake) == 'done'
    doc = db.get(Document, doc_id)
    assert doc.status == 'done' and doc.needs_review is False and doc.attempts == 1
    assert doc.total == Decimal('269.50') and doc.currency == 'EUR'
    assert doc.number_key == 'INV20250042'
    versions = db.query(Extraction).filter_by(document_id=doc_id).all()
    assert [(v.version, v.source) for v in versions] == [(1, 'ai')]
    assert versions[0].data['total']['value'] == '269.50'
    assert stages(db, doc_id) == [('extract', 'ok'), ('validate', 'ok')]


def test_second_copy_is_flagged_as_duplicate(db):
    first, second = add_doc(db, name='a.pdf'), add_doc(db, name='b.pdf')
    process_document(db, first, fake)
    process_document(db, second, fake)
    doc = db.get(Document, second)
    issues = db.query(Extraction).filter_by(document_id=second).one().issues
    assert doc.needs_review is True
    assert [i['code'] for i in issues] == ['duplicate_invoice']
    assert 'a.pdf' in issues[0]['message']


def test_document_is_processed_only_once(db):
    doc_id = add_doc(db)
    assert process_document(db, doc_id, fake) == 'done'
    assert process_document(db, doc_id, fake) == 'skipped'     # same job delivered twice
    assert db.query(Extraction).filter_by(document_id=doc_id).count() == 1


def test_busy_llm_raises_and_a_retry_succeeds(db):
    doc_id = add_doc(db)
    with pytest.raises(LLMUnavailable):
        process_document(db, doc_id, busy)
    wait_for_retry(db, doc_id, 'LLM busy', 120)                 # what the Celery task does
    doc = db.get(Document, doc_id)
    assert (doc.status, doc.error_code) == ('queued', 'llm_unavailable')
    assert process_document(db, doc_id, fake) == 'done'
    db.refresh(doc)
    assert doc.attempts == 2 and doc.error_code is None
    assert ('extract', 'retry') in stages(db, doc_id)


def test_corrupt_file_fails_with_its_code(db, tmp_path):
    path = tmp_path / 'broken'
    path.write_bytes(b'%PDF-1.4\nthis is not really a pdf')
    doc_id = add_doc(db, text=None, path=str(path), name='broken.pdf')
    assert process_document(db, doc_id, fake) == 'failed'
    doc = db.get(Document, doc_id)
    assert (doc.status, doc.error_code) == ('failed', 'corrupt_file')
    assert stages(db, doc_id) == [('parse', 'failed')]


def test_empty_text_fails_without_retry(db):
    doc_id = add_doc(db, text='   ')
    assert process_document(db, doc_id, fake) == 'failed'
    assert db.get(Document, doc_id).error_code == 'extraction_failed'


def test_unexpected_error_is_recorded_not_raised(db):
    doc_id = add_doc(db, text=None, path='/does/not/exist')
    assert process_document(db, doc_id, fake) == 'failed'
    doc = db.get(Document, doc_id)
    assert doc.error_code == 'internal_error'
    assert '/does/not/exist' not in doc.error_message           # no internals in the API