"""Write a document's chunks and embeddings. Called by the worker after validation."""
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk
from app.search.chunks import MAX_CHUNKS, chunk_text, header_text
from app.search.embed import Embedder


def index_document(db: Session, doc: Document, embedder: Embedder) -> int:
    """Replace the document's chunks. Returns how many were written. Does not commit."""
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    texts = [header_text(doc.filename, doc.invoice_number, doc.supplier_name,
                         doc.invoice_date, doc.total, doc.currency)]
    texts += chunk_text(doc.text or '')
    texts = texts[:MAX_CHUNKS]
    vectors = embedder.embed(texts)
    for number, (text, vector) in enumerate(zip(texts, vectors)):
        db.add(DocumentChunk(document_id=doc.id, chunk_index=number, text=text, embedding=vector))
    return len(texts)