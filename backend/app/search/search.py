"""Keyword, semantic and hybrid search over processed documents."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk
from app.search.embed import Embedder
from app.search.rank import rrf_merge

SNIPPET_CHARS = 240
HEADLINE_OPTIONS = 'MaxFragments=1, MaxWords=30, MinWords=12, StartSel=[, StopSel=]'


@dataclass
class Filters:
    status: str | None = None
    needs_review: bool | None = None
    supplier: str | None = None          # part of the name, any case
    currency: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    min_total: Decimal | None = None
    max_total: Decimal | None = None


@dataclass
class Hit:
    document: Document
    score: float
    snippet: str | None


def apply_filters(query: Select, f: Filters) -> Select:
    """The same structured filters for every search mode. All values are bound parameters,
    never pasted into SQL, so user input cannot change the query."""
    if f.status:
        query = query.where(Document.status == f.status)
    if f.needs_review is not None:
        query = query.where(Document.needs_review == f.needs_review)
    if f.supplier:
        query = query.where(Document.supplier_name.icontains(f.supplier, autoescape=True))  # % and _ are literal
    if f.currency:
        query = query.where(Document.currency == f.currency.upper())
    if f.date_from:
        query = query.where(Document.invoice_date >= f.date_from)
    if f.date_to:
        query = query.where(Document.invoice_date <= f.date_to)
    if f.min_total is not None:
        query = query.where(Document.total >= f.min_total)
    if f.max_total is not None:
        query = query.where(Document.total <= f.max_total)
    return query


def filter_only(db: Session, f: Filters, limit: int) -> list[Hit]:
    query = apply_filters(select(Document), f)
    query = query.order_by(Document.invoice_date.desc().nulls_last(), Document.created_at.desc()).limit(limit)
    return [Hit(doc, 0.0, None) for doc in db.scalars(query)]


def keyword_search(db: Session, q: str, f: Filters, limit: int) -> list[Hit]:
    """Postgres full-text search. websearch_to_tsquery understands what people type:
    words, "exact phrases", OR, and -excluded words, and never raises a syntax error."""
    tsq = func.websearch_to_tsquery('english', q)
    rank = func.ts_rank_cd(Document.search_vector, tsq)
    snippet = func.ts_headline('english', func.coalesce(Document.text, ''), tsq, HEADLINE_OPTIONS)
    query = select(Document, rank.label('score'), snippet.label('snippet')) \
        .where(Document.search_vector.op('@@')(tsq))
    query = apply_filters(query, f).order_by(rank.desc(), Document.id).limit(limit)
    return [Hit(doc, float(score), text) for doc, score, text in db.execute(query)]


def semantic_search(db: Session, q: str, f: Filters, limit: int, embedder: Embedder) -> list[Hit]:
    """Nearest chunks by cosine distance, then the best chunk per document.
    We take more chunks than we need because one document can own several of the nearest."""
    vector = embedder.embed([q])[0]
    distance = DocumentChunk.embedding.cosine_distance(vector)
    query = select(DocumentChunk.document_id, DocumentChunk.text, distance.label('distance')) \
        .join(Document, Document.id == DocumentChunk.document_id)
    query = apply_filters(query, f).order_by(distance).limit(limit * 10)
    best: dict = {}
    for doc_id, text, dist in db.execute(query):
        if doc_id not in best:
            best[doc_id] = (float(dist), text)
            if len(best) == limit:
                break
    if not best:
        return []
    docs = {d.id: d for d in db.scalars(select(Document).where(Document.id.in_(list(best))))}
    return [Hit(docs[doc_id], round(1 - dist, 4), text[:SNIPPET_CHARS]) for doc_id, (dist, text) in best.items()]


def hybrid_search(db: Session, q: str, f: Filters, limit: int, embedder: Embedder) -> list[Hit]:
    """Both searches, merged by rank (RRF). Keyword finds exact numbers and names;
    semantic finds the same meaning in other words."""
    keyword = keyword_search(db, q, f, limit * 2)
    semantic = semantic_search(db, q, f, limit * 2, embedder)
    by_id = {h.document.id: h for h in semantic}
    by_id.update({h.document.id: h for h in keyword})     # keyword snippets highlight the words
    merged = rrf_merge([h.document.id for h in keyword], [h.document.id for h in semantic])
    return [Hit(by_id[doc_id].document, round(score, 5), by_id[doc_id].snippet)
            for doc_id, score in merged[:limit]]