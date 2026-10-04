import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .db import init_db
from .job_queue import start_worker, stop_worker, worker_status
from .main import _run_queued_job

logger = logging.getLogger("deepsearch.worker_http")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if not start_worker(_run_queued_job):
        raise RuntimeError(
            "Redis ingestion worker could not start. Check REDIS_URL and "
            "Render Key Value connectivity."
        )
    logger.info("DeepSearch ingestion worker is ready")
    try:
        yield
    finally:
        stop_worker()


app = FastAPI(title="DeepSearch Ingestion Worker", lifespan=lifespan)


@app.get("/")
def root():
    return {"service": "deepsearch-ingestion-worker", "status": "ok"}


@app.get("/health")
def health():
    return {
        "service": "deepsearch-ingestion-worker",
        "status": "ok",
        "worker": worker_status(),
    }
