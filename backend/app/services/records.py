"""Small database helpers shared by the API and the worker."""
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Document, Extraction, ProcessingEvent
from app.schemas.invoice import InvoiceExtraction
from app.schemas.validation import ValidationReport
from app.validation.duplicates import SeenInvoice, remember


def add_event(db: Session, doc_id: uuid.UUID, stage: str, status: str,
              message: str | None = None, duration_ms: int | None = None) -> None:
    db.add(ProcessingEvent(document_id=doc_id, stage=stage, status=status,
                           message=(message or '')[:2000] or None, duration_ms=duration_ms))


def current_extraction(db: Session, doc_id: uuid.UUID) -> Extraction | None:
    return db.scalar(select(Extraction).where(Extraction.document_id == doc_id)
                     .order_by(Extraction.version.desc()).limit(1))


def seen_for(db: Session, inv: InvoiceExtraction, exclude_id: uuid.UUID) -> list[SeenInvoice]:
    """Earlier invoices that could be duplicates of inv. check_duplicates only ever matches on the
    same number key or the same supplier key, so we load only those rows, not the whole table."""
    me = remember('', inv)
    matches = []
    if me.number_key:
        matches.append(Document.number_key == me.number_key)
    if me.supplier_key:
        matches.append(Document.supplier_key == me.supplier_key)
    if not matches:
        return []
    rows = db.scalars(select(Document).where(
        Document.id != exclude_id, Document.status == 'done', or_(*matches))).all()
    return [SeenInvoice(doc_id=row.filename, number=row.invoice_number, number_key=row.number_key,
                        digits=row.number_digits, supplier_key=row.supplier_key,
                        invoice_date=row.invoice_date, total=row.total) for row in rows]


def save_result(db: Session, doc: Document, inv: InvoiceExtraction, report: ValidationReport,
                source: str, changes: list[dict] | None = None) -> int:
    """Add a new extraction version and copy its key values onto the document. Does not commit."""
    last = db.scalar(select(func.max(Extraction.version)).where(Extraction.document_id == doc.id))
    version = (last or 0) + 1
    db.add(Extraction(
        document_id=doc.id, version=version, source=source,
        data=inv.model_dump(mode='json'),
        issues=[issue.model_dump(mode='json') for issue in report.issues],
        needs_review=report.needs_review, changes=changes,
        prompt_version=inv.prompt_version, model=inv.model,
    ))
    key = remember(str(doc.id), inv)
    doc.invoice_number = key.number
    doc.number_key = key.number_key
    doc.number_digits = key.digits
    doc.supplier_name = inv.supplier_name.value
    doc.supplier_key = key.supplier_key
    doc.invoice_date = inv.invoice_date.value
    doc.total = inv.total.value
    doc.currency = inv.currency.value
    doc.needs_review = report.needs_review
    return version