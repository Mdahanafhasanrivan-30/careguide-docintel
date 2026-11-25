import redis
from celery.result import AsyncResult
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import documents
from app.core.config import settings
from app.core.security import require_api_key
from app.db.session import engine
from app.workers.celery_app import celery_app
from app.workers.tasks import ping
from app.api import documents, search

app = FastAPI(title="Document Intelligence API")
app.include_router(documents.router)
app.include_router(search.router)
@app.get("/health")
def health():
    status = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        status["db"] = "ok"
    except Exception:
        status["db"] = "error"  # never return exception text: it can leak internals
    try:
        redis.Redis.from_url(settings.redis_url).ping()
        status["redis"] = "ok"
    except Exception:
        status["redis"] = "error"
    code = 200 if all(v == "ok" for v in status.values()) else 503
    return JSONResponse(status_code=code, content=status)


@app.post("/api/v1/ping", status_code=202, dependencies=[Depends(require_api_key)])
def trigger_ping(message: str = "hello"):
    result = ping.delay(message)  # puts a job on the Redis queue and returns at once
    return {"task_id": result.id}


@app.get("/api/v1/ping/{task_id}", dependencies=[Depends(require_api_key)])
def ping_status(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    return {
        "task_id": task_id,
        "state": result.state,
        "result": result.result if result.successful() else None,
    }
