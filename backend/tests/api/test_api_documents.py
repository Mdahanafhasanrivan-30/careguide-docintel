"""REST endpoints with a real PostgreSQL. Celery is replaced by the 'queued' fixture."""
import uuid

from fastapi.testclient import TestClient

from app.api import documents as documents_api
from app.core.config import settings
from app.db.models import Document
from app.extraction.llm import FakeLLMClient
from app.main import app
from app.services.processing import process_document
from tests.test_extract import SOURCE, good_answer

CSV = b'item,amount\nWidget,10\n'


def upload(client, *files):
    return client.post('/api/v1/documents', files=[('files', f) for f in files])


def processed(db) -> uuid.UUID:
    doc = Document(filename='inv.pdf', size_bytes=1, sha256='a' * 64, storage_path='/x',
                   status='queued', text=SOURCE)
    db.add(doc)
    db.commit()
    process_document(db, doc.id, lambda: FakeLLMClient(good_answer()))
    return doc.id


def test_api_key_is_required(db):
    with TestClient(app) as anonymous:
        assert anonymous.get('/api/v1/documents').status_code == 401


def test_upload_queues_a_job(client, queued, storage):
    r = upload(client, ('a.csv', CSV, 'text/csv'))
    assert r.status_code == 202
    item = r.json()[0]
    assert item['status'] == 'queued' and item['already_uploaded'] is False
    assert queued == [uuid.UUID(item['id'])]
    assert len(list(storage.iterdir())) == 1
    detail = client.get(f"/api/v1/documents/{item['id']}").json()
    assert detail['status'] == 'queued' and detail['extraction'] is None


def test_same_bytes_twice_is_one_document(client, queued):
    first = upload(client, ('a.csv', CSV, 'text/csv')).json()[0]
    again = upload(client, ('copy.csv', CSV, 'text/csv')).json()[0]
    assert again['id'] == first['id'] and again['already_uploaded'] is True
    assert len(queued) == 1                                     # no second job


def test_bad_files_are_rejected_one_by_one(client, queued):
    r = upload(client, ('empty.csv', b'', 'text/csv'),
               ('virus.pdf', b'MZ\x90\x00\x03\x00\x00\x00' + bytes(300), 'application/pdf'),
               ('good.csv', CSV, 'text/csv'))
    assert r.status_code == 202
    codes = [(i['filename'], i['status'], i['error_code']) for i in r.json()]
    assert codes == [('empty.csv', 'rejected', 'empty_file'),
                     ('virus.pdf', 'rejected', 'unsupported_file_type'),
                     ('good.csv', 'queued', None)]
    assert len(queued) == 1


def test_file_too_large(client, monkeypatch):
    monkeypatch.setattr(documents_api, 'MAX_FILE_BYTES', 10)
    item = upload(client, ('a.csv', CSV, 'text/csv')).json()[0]
    assert item['error_code'] == 'file_too_large'


def test_too_many_files(client, monkeypatch):
    monkeypatch.setattr(settings, 'max_files_per_upload', 2)
    r = upload(client, *[(f'{n}.csv', CSV + bytes([65 + n]), 'text/csv') for n in range(3)])
    assert r.status_code == 413


def test_path_in_filename_is_dropped(client, storage):
    item = upload(client, ('../../etc/evil.csv', CSV, 'text/csv')).json()[0]
    assert item['filename'] == 'evil.csv'
    assert all(p.parent == storage for p in storage.iterdir())


def test_unknown_document_is_404(client):
    assert client.get(f'/api/v1/documents/{uuid.uuid4()}').status_code == 404


def test_list_filters_by_status(client, db):
    processed(db)
    upload(client, ('a.csv', CSV, 'text/csv'))
    assert [d['status'] for d in client.get('/api/v1/documents?status=done').json()] == ['done']
    assert len(client.get('/api/v1/documents').json()) == 2
    assert client.get('/api/v1/documents?needs_review=false').json()[0]['total'] == '269.50'


def test_correction_adds_a_version_and_revalidates(client, db):
    doc_id = processed(db)
    wrong = client.patch(f'/api/v1/documents/{doc_id}/extraction', json={'fields': {'total': '300.00'}})
    assert wrong.status_code == 200
    body = wrong.json()
    assert body['version'] == 2 and body['source'] == 'manual'
    assert body['needs_review'] is True
    assert 'total_mismatch' in [i['code'] for i in body['issues']]

    fixed = client.patch(f'/api/v1/documents/{doc_id}/extraction', json={'fields': {'total': '269.50'}}).json()
    assert fixed['version'] == 3 and fixed['needs_review'] is False

    history = client.get(f'/api/v1/documents/{doc_id}/history').json()
    assert [v['source'] for v in history['versions']] == ['ai', 'manual', 'manual']
    assert history['versions'][1]['changes'] == [{'field': 'total', 'old': '269.50', 'new': '300.00'}]
    assert [e['stage'] for e in history['events']][-2:] == ['correct', 'correct']


def test_bad_correction_is_422(client, db):
    doc_id = processed(db)
    r = client.patch(f'/api/v1/documents/{doc_id}/extraction', json={'fields': {'total': 'lots'}})
    assert r.status_code == 422
    assert r.json()['detail']['field'] == 'total'


def test_cannot_correct_before_processing(client):
    item = upload(client, ('a.csv', CSV, 'text/csv')).json()[0]
    r = client.patch(f"/api/v1/documents/{item['id']}/extraction", json={'fields': {'total': '1'}})
    assert r.status_code == 409


def test_reprocess_failed_document(client, db, queued):
    doc = Document(filename='x.pdf', size_bytes=1, sha256='b' * 64, storage_path='/x',
                   status='failed', error_code='llm_unavailable', error_message='busy')
    db.add(doc)
    db.commit()
    r = client.post(f'/api/v1/documents/{doc.id}/reprocess')
    assert r.status_code == 202
    assert r.json()['status'] == 'queued' and r.json()['error_code'] is None
    assert queued == [doc.id]


def test_done_document_needs_force(client, db, queued):
    doc_id = processed(db)
    assert client.post(f'/api/v1/documents/{doc_id}/reprocess').status_code == 409
    assert client.post(f'/api/v1/documents/{doc_id}/reprocess?force=true').status_code == 202
    assert db.get(Document, doc_id).text is None               # from scratch: parse again


def test_reprocess_all_failed(client, db, queued):
    for n in range(3):
        db.add(Document(filename=f'{n}.pdf', size_bytes=1, sha256=str(n) * 64, storage_path='/x',
                        status='failed' if n < 2 else 'done'))
    db.commit()
    r = client.post('/api/v1/documents/reprocess-failed')
    assert r.status_code == 202 and len(r.json()['queued']) == 2
    assert len(queued) == 2