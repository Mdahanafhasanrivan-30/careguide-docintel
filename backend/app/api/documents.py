import mimetypes
import uuid
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import require_api_key
from app.db.models import IN_PROGRESS, Document, Extraction, ProcessingEvent
from app.db.session import get_db
from app.pipeline.detect import detect_type
from app.pipeline.errors import DocumentError
from app.pipeline.parser import MAX_FILE_BYTES
from app.schemas.api import (
    CorrectionIn, DocumentDetail, DocumentSummary, EventOut, History, ReprocessResult,
    UploadResult, VersionOut,DocumentText
)
from app.schemas.invoice import InvoiceExtraction
from app.services.corrections import CorrectionError, apply_corrections
from app.services.records import add_event, current_extraction, save_result, seen_for
from app.services.storage import delete_file, save_upload, sha256_hex
from app.validation.validate import validate_invoice

router = APIRouter(prefix='/api/v1/documents', tags=['documents'],
                   dependencies=[Depends(require_api_key)])

CHUNK = 1024 * 1024


def enqueue(doc_id: uuid.UUID) -> None:
    """Put a processing job on the Redis queue. Tests replace this function."""
    from app.workers.tasks import process_document_task
    process_document_task.delay(str(doc_id))


def _queue(db: Session, doc: Document) -> None:
    """Call only AFTER commit: otherwise a fast worker could look for a row that is not saved yet."""
    try:
        enqueue(doc.id)
    except Exception:  # Redis down: do not lose the document, mark it so it can be reprocessed
        doc.status, doc.error_code = 'failed', 'queue_unavailable'
        doc.error_message = 'Could not queue the job; reprocess it when the queue is back'
        add_event(db, doc.id, 'upload', 'failed', doc.error_message)
        db.commit()


def _clean_name(raw: str | None) -> str:
    name = PurePosixPath((raw or '').replace('\\', '/')).name   # 'C:\\x\\a.pdf' and '../a.pdf' -> 'a.pdf'
    return (name or 'unnamed')[:255]


def _read_limited(upload: UploadFile) -> bytes | None:
    """Read at most MAX_FILE_BYTES; None if the file is bigger."""
    data = bytearray()
    while chunk := upload.file.read(CHUNK):
        data += chunk
        if len(data) > MAX_FILE_BYTES:
            return None
    return bytes(data)


def _accept(db: Session, upload: UploadFile) -> UploadResult:
    name = _clean_name(upload.filename)
    data = _read_limited(upload)
    if data is None:
        return UploadResult(filename=name, status='rejected', error_code='file_too_large',
                            error=f'File is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB')
    if not data:
        return UploadResult(filename=name, status='rejected', error_code='empty_file', error='File is empty')
    try:
        detect_type(data, name)          # cheap check now; the worker does the real parsing
    except DocumentError as exc:
        return UploadResult(filename=name, status='rejected', error_code=exc.code, error=exc.message)

    digest = sha256_hex(data)
    existing = db.scalar(select(Document).where(Document.sha256 == digest))
    if existing:
        return UploadResult(filename=name, id=existing.id, status=existing.status, already_uploaded=True)

    path = save_upload(data)
    doc = Document(filename=name, size_bytes=len(data), sha256=digest, storage_path=path, status='queued')
    db.add(doc)
    try:
        db.flush()                       # INSERT now, so a duplicate sha256 fails here
    except IntegrityError:               # the same file arrived twice at the same moment
        db.rollback()
        delete_file(path)
        existing = db.scalar(select(Document).where(Document.sha256 == digest))
        return UploadResult(filename=name, id=existing.id, status=existing.status, already_uploaded=True)
    add_event(db, doc.id, 'upload', 'ok', f'{len(data)} bytes')
    db.commit()
    _queue(db, doc)
    return UploadResult(filename=name, id=doc.id, status=doc.status)


@router.post('', status_code=202, response_model=list[UploadResult])
def upload_documents(files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    if len(files) > settings.max_files_per_upload:
        raise HTTPException(413, f'At most {settings.max_files_per_upload} files per request')
    return [_accept(db, upload) for upload in files]


@router.get('', response_model=list[DocumentSummary])
def list_documents(status: str | None = None, needs_review: bool | None = None,
                   limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                   db: Session = Depends(get_db)):
    query = select(Document)
    if status:
        query = query.where(Document.status == status)
    if needs_review is not None:
        query = query.where(Document.needs_review == needs_review)
    query = query.order_by(Document.created_at.desc(), Document.id).limit(limit).offset(offset)
    return db.scalars(query).all()


@router.post('/reprocess-failed', status_code=202, response_model=ReprocessResult)
def reprocess_failed(limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)):
    docs = db.scalars(select(Document).where(Document.status == 'failed')
                      .order_by(Document.created_at).limit(limit)).all()
    for doc in docs:
        _reset(db, doc, from_scratch=False)
    db.commit()
    for doc in docs:
        _queue(db, doc)
    return ReprocessResult(queued=[doc.id for doc in docs])


def _get(db: Session, doc_id: uuid.UUID) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, 'Document not found')
    return doc


def _detail(db: Session, doc: Document) -> DocumentDetail:
    out = DocumentDetail.model_validate(doc)
    current = current_extraction(db, doc.id)
    if current:
        out.version, out.source = current.version, current.source
        out.extraction, out.issues = current.data, current.issues
    return out


@router.get('/{doc_id}', response_model=DocumentDetail)
def get_document(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    return _detail(db, _get(db, doc_id))


@router.get('/{doc_id}/history', response_model=History)
def get_history(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    _get(db, doc_id)
    events = db.scalars(select(ProcessingEvent).where(ProcessingEvent.document_id == doc_id)
                        .order_by(ProcessingEvent.id)).all()
    versions = db.scalars(select(Extraction).where(Extraction.document_id == doc_id)
                          .order_by(Extraction.version)).all()
    return History(
        events=[EventOut.model_validate(e) for e in events],
        versions=[VersionOut(version=v.version, source=v.source, needs_review=v.needs_review,
                             issue_count=len(v.issues), changes=v.changes, created_at=v.created_at)
                  for v in versions],
    )


@router.patch('/{doc_id}/extraction', response_model=DocumentDetail)
def correct_extraction(doc_id: uuid.UUID, body: CorrectionIn, db: Session = Depends(get_db)):
    doc = _get(db, doc_id)
    current = current_extraction(db, doc_id)
    if doc.status != 'done' or current is None:
        raise HTTPException(409, f'Document is {doc.status}; only processed documents can be corrected')
    try:
        fixed, changes = apply_corrections(InvoiceExtraction.model_validate(current.data), body.fields)
    except CorrectionError as exc:
        raise HTTPException(422, {'field': exc.field, 'message': exc.message})
    report = validate_invoice(fixed, seen_for(db, fixed, doc.id))   # the rules run again on the new values
    version = save_result(db, doc, fixed, report, source='manual', changes=changes)
    add_event(db, doc.id, 'correct', 'ok',
              f'version {version}: ' + ', '.join(c['field'] for c in changes))
    try:
        db.commit()
    except IntegrityError:               # someone else saved a version at the same moment
        db.rollback()
        raise HTTPException(409, 'The document changed meanwhile; reload it and try again')
    return _detail(db, doc)


def _reset(db: Session, doc: Document, from_scratch: bool) -> None:
    if from_scratch:
        doc.text = None                  # parse (and OCR) the file again
    before = f'{doc.status} ({doc.error_code})' if doc.error_code else doc.status
    doc.status, doc.error_code, doc.error_message = 'queued', None, None
    add_event(db, doc.id, 'reprocess', 'ok', f'was {before}; from scratch: {from_scratch}')


@router.post('/{doc_id}/reprocess', status_code=202, response_model=DocumentSummary)
def reprocess(doc_id: uuid.UUID, force: bool = False, db: Session = Depends(get_db)):
    """failed -> queued. force=true also re-runs a done or stuck document from scratch."""
    doc = _get(db, doc_id)
    allowed = doc.status == 'failed' or (force and (doc.status == 'done' or doc.status in IN_PROGRESS))
    if not allowed:
        raise HTTPException(409, f'Document is {doc.status}; only failed documents can be reprocessed '
                                 '(use force=true for done or stuck ones)')
    _reset(db, doc, from_scratch=force)
    db.commit()
    _queue(db, doc)
    return doc




TEXT_LIMIT = 200_000      # characters sent to the browser; a 1000-page PDF has far more


@router.get('/{doc_id}/file')
def get_file(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    """The original upload, shown inline (PDF viewer or image) in the review page."""
    doc = _get(db, doc_id)
    path = Path(doc.storage_path)
    if not path.is_file():
        raise HTTPException(404, 'The stored file is missing')
    media_type = doc.mime_type or mimetypes.guess_type(doc.filename)[0] or 'application/octet-stream'
    return FileResponse(path, media_type=media_type, filename=doc.filename, content_disposition_type='inline',
                        headers={'X-Content-Type-Options': 'nosniff'})   # the browser must not guess another type


@router.get('/{doc_id}/text', response_model=DocumentText)
def get_text(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    """The parsed text, for the review page and for spreadsheets that a browser cannot show."""
    text = _get(db, doc_id).text or ''
    return DocumentText(text=text[:TEXT_LIMIT], length=len(text), truncated=len(text) > TEXT_LIMIT)