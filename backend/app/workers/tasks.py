import time

from celery.utils.log import get_task_logger

from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="ping")
def ping(message: str = "hello") -> str:
    logger.info("ping received: %s", message)
    time.sleep(3)  # pretend this is slow OCR work
    return f"pong: {message}"
