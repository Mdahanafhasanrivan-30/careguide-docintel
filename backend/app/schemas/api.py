"""What the REST API accepts and returns. Kept apart from the database models on purpose:
the API contract can stay stable while tables change."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class UploadResult(BaseModel):
    filename: str
    id: uuid.UUID | None = None
    status: str                       # queued | done | ... | rejected
    already_uploaded: bool = False    # same bytes were uploaded before: no new job
    error_code: str | None = None
    error: str | None = None


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    status: str
    needs_review: bool | None
    error_code: str | None
    error_message: str | None
    file_kind: str | None
    page_count: int | None
    attempts: int
    invoice_number: str | None
    supplier_name: str | None
    invoice_date: date | None
    total: Decimal | None
    currency: str | None
    created_at: datetime
    updated_at: datetime


class DocumentDetail(DocumentSummary):
    version: int | None = None
    source: str | None = None                 # 'ai' or 'manual'
    extraction: dict | None = None            # InvoiceExtraction as JSON
    issues: list[dict] = Field(default_factory=list)


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage: str
    status: str
    message: str | None
    duration_ms: int | None
    created_at: datetime


class VersionOut(BaseModel):
    version: int
    source: str
    needs_review: bool
    issue_count: int
    changes: list[dict] | None
    created_at: datetime


class History(BaseModel):
    events: list[EventOut]
    versions: list[VersionOut]


class CorrectionIn(BaseModel):
    # e.g. {"fields": {"total": "1084.02", "currency": "USD"}}; "" or null clears a field
    fields: dict[str, str | None] = Field(min_length=1)


class ReprocessResult(BaseModel):
    queued: list[uuid.UUID]



class SearchHit(BaseModel):
    document: DocumentSummary
    score: float                      # keyword: ts_rank; semantic: cosine similarity; hybrid: RRF
    snippet: str | None


class SearchResponse(BaseModel):
    query: str
    mode: str                         # keyword | semantic | hybrid | filter (no query text)
    count: int
    hits: list[SearchHit]