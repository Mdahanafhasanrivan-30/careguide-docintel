"""Build the search index for documents that are done but have no chunks
(everything processed before Phase 5, or an index that failed). --all rebuilds every one.

Run inside Docker:  dcrun python -m scripts.reindex
"""
import argparse

from sqlalchemy import exists, select

from app.db.models import Document, DocumentChunk
from app.db.session import SessionLocal
from app.search.embed import get_embedder
from app.search.index import index_document


def main() -> int:
    ap = argparse.ArgumentParser(description='Build semantic-search chunks for processed documents')
    ap.add_argument('--all', action='store_true', help='rebuild every done document, not only missing ones')
    args = ap.parse_args()
    embedder = get_embedder()           # first run downloads the model (~70 MB)
    with SessionLocal() as db:
        query = select(Document).where(Document.status == 'done')
        if not args.all:
            query = query.where(~exists().where(DocumentChunk.document_id == Document.id))
        docs = db.scalars(query).all()
        for doc in docs:
            count = index_document(db, doc, embedder)
            db.commit()
            print(f'{doc.filename}: {count} chunks')
        print(f'indexed {len(docs)} documents')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())