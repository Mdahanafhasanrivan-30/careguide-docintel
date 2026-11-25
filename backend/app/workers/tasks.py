import time
import uuid

from celery.utils.log import get_task_logger

from app.db.session import SessionLocal
from app.extraction.errors import LLMUnavailable
from app.extraction.llm import make_client
from app.services.processing import fail, process_document, wait_for_retry
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)

LLM_RETRIES = 3            # worker-level tries after the client's own 15/30/60 s loop gives up
RETRY_BASE_SECONDS = 120   # 2, 4, 8 minutes: long enough for a free-tier 503 burst to pass


@celery_app.task(name="ping")
def ping(message: str = "hello") -> str:
    logger.info("ping received: %s", message)
    time.sleep(3)  # pretend this is slow OCR work
    return f"pong: {message}"


@celery_app.task(name='process_document', bind=True, max_retries=LLM_RETRIES)
def process_document_task(self, doc_id: str) -> str:
    document_id = uuid.UUID(doc_id)
    with SessionLocal() as db:
        try:
            return process_document(db, document_id, make_client)
        except LLMUnavailable as exc:
            tries = self.request.retries
            if tries >= LLM_RETRIES:
                fail(db, document_id, 'extract', exc.code,
                     f'{exc.message}; gave up after {tries + 1} worker attempts. '
                     'Use POST /api/v1/documents/{id}/reprocess later.')
                return 'failed'
            wait = RETRY_BASE_SECONDS * 2**tries
            wait_for_retry(db, document_id, exc.message, wait)
            logger.warning('LLM busy for %s; retry %d in %d s', doc_id, tries + 1, wait)
            raise self.retry(countdown=wait)