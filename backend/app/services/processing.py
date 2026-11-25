"""The whole pipeline for one stored document: parse -> extract -> validate -> save.
Celery calls process_document; tests call it directly with a FakeLLMClient."""
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import and_, func, or_, update
from sqlalchemy.orm import Session

from app.db.models import IN_PROGRESS, Document
from app.extraction.errors import ExtractionError, LLMUnavailable
from app.extraction.extract import extract_invoice
from app.extraction.llm import LLMClient
from app.pipeline.errors import DocumentError
from app.pipeline.parser import parse_document
from app.search.embed import Embedder
from app.search.index import index_document
from app.services.records import add_event, save_result, seen_for
from app.validation.validate import validate_invoice

logger = logging.getLogger(__name__)
STALE_AFTER = timedelta(minutes=30)   # a document 'in progress' this long belongs to a dead worker


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def claim(db: Session, doc_id: uuid.UUID) -> bool:
    """Move the document to 'parsing' in ONE UPDATE. If two workers get the same job
    (acks_late can deliver a job twice), only one UPDATE matches the row; the other skips."""
    stale = datetime.now(timezone.utc) - STALE_AFTER
    result = db.execute(
        update(Document)
        .where(Document.id == doc_id,
               or_(Document.status == 'queued',
                   and_(Document.status.in_(IN_PROGRESS), Document.updated_at < stale)))
        .values(status='parsing', attempts=Document.attempts + 1,
                error_code=None, error_message=None, updated_at=func.now())
    )
    db.commit()
    return result.rowcount == 1


def fail(db: Session, doc_id: uuid.UUID, stage: str, code: str, message: str) -> None:
    doc = db.get(Document, doc_id)
    doc.status, doc.error_code, doc.error_message = 'failed', code, message[:2000]
    add_event(db, doc_id, stage, 'failed', f'{code}: {message}')
    db.commit()


def wait_for_retry(db: Session, doc_id: uuid.UUID, message: str, seconds: int) -> None:
    """Back to 'queued' so the retried job can claim it again; the reason stays visible."""
    doc = db.get(Document, doc_id)
    doc.status, doc.error_code = 'queued', 'llm_unavailable'
    doc.error_message = f'{message} (next try in {seconds} s)'
    add_event(db, doc_id, 'extract', 'retry', doc.error_message)
    db.commit()

def _index(db: Session, doc: Document, make_embedder: Callable[[], Embedder]) -> None:
    """Build the search index. A failure here must not undo a good extraction: the document
    stays 'done', the event says the index failed, and scripts/reindex.py can repair it."""
    started = time.perf_counter()
    try:
        count = index_document(db, doc, make_embedder())
        add_event(db, doc.id, 'index', 'ok', f'{count} chunks', _ms(started))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception('search index failed for %s', doc.id)
        add_event(db, doc.id, 'index', 'failed', 'Search index not updated; see the worker log')
        db.commit()

def process_document(db: Session, doc_id: uuid.UUID, make_llm: Callable[[], LLMClient],
                     make_embedder: Callable[[], Embedder] | None = None) -> str:
    """Returns 'done', 'failed' or 'skipped'. Raises LLMUnavailable so the caller can retry later."""
    if not claim(db, doc_id):
        logger.info('document %s is not queued; skipped', doc_id)
        return 'skipped'
    doc = db.get(Document, doc_id)
    stage = 'parse'
    try:
        if doc.text is None:            # a retry after a busy LLM does not OCR the file again
            started = time.perf_counter()
            parsed = parse_document(Path(doc.storage_path).read_bytes(), doc.filename)
            doc.text = parsed.full_text()
            doc.page_count, doc.file_kind, doc.mime_type = parsed.page_count, parsed.file_kind, parsed.mime_type
            add_event(db, doc.id, 'parse', 'ok',
                      f'{parsed.page_count} pages, {len(parsed.warnings)} warnings', _ms(started))
        stage, doc.status = 'extract', 'extracting'
        db.commit()

        started = time.perf_counter()
        inv = extract_invoice(doc.text, make_llm())
        add_event(db, doc.id, 'extract', 'ok',
                  f'{inv.model}, {inv.input_tokens} in / {inv.output_tokens} out tokens, '
                  f'{len(inv.warnings)} warnings', _ms(started))
        stage, doc.status = 'validate', 'validating'
        db.commit()

        started = time.perf_counter()
        report = validate_invoice(inv, seen_for(db, inv, doc.id))
        version = save_result(db, doc, inv, report, source='ai')
        doc.status = 'done'
        add_event(db, doc.id, 'validate', 'ok',
                  f'version {version}, {len(report.issues)} issues', _ms(started))
        db.commit()
        if make_embedder is not None:    # None in the Phase 4 tests: no index
            _index(db, doc, make_embedder)
        return 'done'
    except LLMUnavailable:
        db.rollback()
        raise                            # temporary: the Celery task decides when to try again
    except (DocumentError, ExtractionError) as exc:
        db.rollback()
        fail(db, doc_id, stage, exc.code, exc.message)
        return 'failed'
    except Exception:
        db.rollback()
        logger.exception('unexpected error while processing %s', doc_id)
        fail(db, doc_id, stage, 'internal_error', 'Unexpected error; see the worker log')
        return 'failed'