from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "docintel",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_track_started=True,        # report STARTED, not just PENDING and SUCCESS
    task_acks_late=True,            # a job is removed from the queue only after it finishes
    worker_prefetch_multiplier=1,   # each worker takes one slow job at a time
    task_reject_on_worker_lost=True,  # a worker killed mid-job (out of memory) puts the job back
)
