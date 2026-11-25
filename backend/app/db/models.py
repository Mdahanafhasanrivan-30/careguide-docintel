import uuid
from datetime import date, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger, Computed, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.search.embed import DIM

# queued -> parsing -> extracting -> validating -> done, or failed at any step
IN_PROGRESS = ('parsing', 'extracting', 'validating')

# Keyword search reads this. Postgres keeps it up to date by itself (a generated column), also
# after a correction. left(...) keeps the tsvector under Postgres's 1 MB limit for huge files.
SEARCH_EXPR = (
    "to_tsvector('english', coalesce(filename, '') || ' ' || coalesce(invoice_number, '') || ' ' || "
    "coalesce(supplier_name, '') || ' ' || left(coalesce(text, ''), 200000))"
)


class Document(Base):
    __tablename__ = 'documents'
    __table_args__ = (Index('ix_documents_search_vector', 'search_vector', postgresql_using='gin'),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64), unique=True)      # same bytes = same upload
    storage_path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str | None] = mapped_column(String(100))
    file_kind: Mapped[str | None] = mapped_column(String(10))
    page_count: Mapped[int | None]
    text: Mapped[str | None] = mapped_column(Text)                     # parse result, kept for retries and search

    status: Mapped[str] = mapped_column(String(20), default='queued', index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    needs_review: Mapped[bool | None] = mapped_column(index=True)

    # Current values, copied from the newest extraction version: used for filters and duplicate checks.
    invoice_number: Mapped[str | None] = mapped_column(Text)
    number_key: Mapped[str | None] = mapped_column(Text, index=True)
    number_digits: Mapped[str | None] = mapped_column(Text)
    supplier_name: Mapped[str | None] = mapped_column(Text)
    supplier_key: Mapped[str | None] = mapped_column(Text, index=True)
    invoice_date: Mapped[date | None]
    total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(10))
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, Computed(SEARCH_EXPR, persisted=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())

    extractions: Mapped[list['Extraction']] = relationship(
        back_populates='document', cascade='all, delete-orphan', order_by='Extraction.version')
    events: Mapped[list['ProcessingEvent']] = relationship(
        back_populates='document', cascade='all, delete-orphan', order_by='ProcessingEvent.id')


class Extraction(Base):
    """One row per version. The AI writes version 1; every manual correction adds a new version.
    Rows are never updated, so the full history of a document's values is kept."""
    __tablename__ = 'extractions'
    __table_args__ = (UniqueConstraint('document_id', 'version'),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    version: Mapped[int]
    source: Mapped[str] = mapped_column(String(10))                    # 'ai' or 'manual'
    data: Mapped[dict] = mapped_column(JSONB)                          # InvoiceExtraction as JSON
    issues: Mapped[list] = mapped_column(JSONB)                        # validation Issue list as JSON
    needs_review: Mapped[bool]
    changes: Mapped[list | None] = mapped_column(JSONB)                # manual only: [{field, old, new}]
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates='extractions')


class ProcessingEvent(Base):
    """Processing history: one row per stage result, failure, retry or correction."""
    __tablename__ = 'processing_events'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    stage: Mapped[str] = mapped_column(String(20))      # upload, parse, extract, validate, correct, reprocess
    status: Mapped[str] = mapped_column(String(20))     # ok, failed, retry
    message: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates='events')


class DocumentChunk(Base):
    """A piece of a document's text and its embedding, for semantic search."""
    __tablename__ = 'document_chunks'
    __table_args__ = (
        Index('ix_document_chunks_embedding_hnsw', 'embedding', postgresql_using='hnsw',
              postgresql_with={'m': 16, 'ef_construction': 64},
              postgresql_ops={'embedding': 'vector_cosine_ops'}),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    chunk_index: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(DIM))