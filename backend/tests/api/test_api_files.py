"""The two endpoints the review page needs: the original file and the parsed text."""
import uuid

from app.db.models import Document
from tests.test_extract import SOURCE

CSV = b'item,amount\nWidget,10\n'


def test_file_is_served_inline_with_its_type(client):
    item = client.post('/api/v1/documents', files=[('files', ('a.csv', CSV, 'text/csv'))]).json()[0]
    r = client.get(f"/api/v1/documents/{item['id']}/file")
    assert r.status_code == 200 and r.content == CSV
    assert r.headers['content-type'].startswith('text/csv')
    assert r.headers['content-disposition'].startswith('inline')
    assert r.headers['x-content-type-options'] == 'nosniff'


def test_missing_document_or_file_is_404(client, db):
    assert client.get(f'/api/v1/documents/{uuid.uuid4()}/file').status_code == 404
    doc = Document(filename='gone.pdf', size_bytes=1, sha256='e' * 64, storage_path='/nowhere/gone.pdf', status='done')
    db.add(doc)
    db.commit()
    r = client.get(f'/api/v1/documents/{doc.id}/file')
    assert r.status_code == 404 and r.json()['detail'] == 'The stored file is missing'


def test_text_is_returned(client, db):
    doc = Document(filename='inv.pdf', size_bytes=1, sha256='f' * 64, storage_path='/x', status='done', text=SOURCE)
    db.add(doc)
    db.commit()
    body = client.get(f'/api/v1/documents/{doc.id}/text').json()
    assert body == {'text': SOURCE, 'length': len(SOURCE), 'truncated': False}


def test_long_text_is_cut(client, db):
    doc = Document(filename='big.pdf', size_bytes=1, sha256='0' * 64, storage_path='/x', status='done', text='x' * 250_000)
    db.add(doc)
    db.commit()
    body = client.get(f'/api/v1/documents/{doc.id}/text').json()
    assert len(body['text']) == 200_000 and body['length'] == 250_000 and body['truncated'] is True