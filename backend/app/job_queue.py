import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from .config import settings
from .db import all_, exe, now

logger = logging.getLogger("deepsearch.queue")

QUEUE_NAME = "deepsearch:ingestion:jobs"
STALE_AFTER_SECONDS = 15 * 60
RECOVERY_INTERVAL_SECONDS = 30

_redis = None
_redis_lock = threading.Lock()
_worker_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _client():
    global _redis
    if _redis is not None:
        return _redis
    if not settings.redis_url:
        return None

    try:
        import redis
    except ImportError:
        return None

    with _redis_lock:
        if _redis is not None:
            return _redis
        try:
            client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=5,
                health_check_interval=30,
            )
            client.ping()
            _redis = client
        except Exception:
            logger.exception("Redis ingestion queue is unavailable")
            _redis = None

    return _redis


def queue_available() -> bool:
    return _client() is not None


def enqueue_job(job_id: str) -> bool:
    client = _client()
    if client is None:
        return False

    try:
        client.rpush(QUEUE_NAME, job_id)
        return True
    except Exception:
        logger.exception("Could not enqueue ingestion job %s", job_id)
        return False


def recover_jobs() -> dict[str, int]:
    client = _client()
    if client is None:
        return {"queued": 0, "stale": 0}

    stale_cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=STALE_AFTER_SECONDS)
    ).isoformat()

    stale_rows = all_(
        """
        SELECT id, file_id
        FROM upload_jobs
        WHERE status='processing' AND updated_at < ?
        ORDER BY updated_at ASC
        LIMIT 50
        """,
        (stale_cutoff,),
    )

    stale_count = 0
    for row in stale_rows:
        job_id = row["id"]
        exe(
            """
            UPDATE upload_jobs
            SET status='queued',
                stage='uploaded',
                progress=10,
                error=?,
                updated_at=?
            WHERE id=? AND status='processing'
            """,
            (
                "Recovered after an interrupted ingestion worker.",
                now(),
                job_id,
            ),
        )
        exe(
            "UPDATE files SET status=? WHERE id=?",
            ("processing", row["file_id"]),
        )
        if enqueue_job(job_id):
            stale_count += 1

    queued_rows = all_(
        """
        SELECT id
        FROM upload_jobs
        WHERE status='queued'
        ORDER BY created_at ASC
        LIMIT 100
        """
    )

    queued_count = 0
    for row in queued_rows:
        if enqueue_job(row["id"]):
            queued_count += 1

    if stale_count or queued_count:
        logger.info(
            "Ingestion queue recovery: stale=%s queued=%s",
            stale_count,
            queued_count,
        )

    return {"queued": queued_count, "stale": stale_count}


def queue_depth() -> int:
    client = _client()
    if client is None:
        return 0
    try:
        return int(client.llen(QUEUE_NAME))
    except Exception:
        return 0


def worker_status() -> dict:
    return {
        "queue": QUEUE_NAME,
        "redis_available": queue_available(),
        "running": bool(_worker_thread and _worker_thread.is_alive()),
        "depth": queue_depth(),
    }


def start_worker(process_job: Callable[[str], None]) -> bool:
    global _worker_thread

    if _worker_thread and _worker_thread.is_alive():
        return True

    if not queue_available():
        logger.warning(
            "Redis ingestion queue unavailable; upload endpoint will use its "
            "development fallback."
        )
        return False

    _stop_event.clear()
    _worker_thread = threading.Thread(
        target=_worker_loop,
        args=(process_job,),
        name="deepsearch-ingestion-worker",
        daemon=True,
    )
    _worker_thread.start()
    logger.info("Persistent ingestion worker started")
    return True


def stop_worker() -> None:
    _stop_event.set()


def _worker_loop(process_job: Callable[[str], None]) -> None:
    last_recovery = 0.0

    while not _stop_event.is_set():
        now_monotonic = time.monotonic()
        if now_monotonic - last_recovery >= RECOVERY_INTERVAL_SECONDS:
            try:
                recover_jobs()
            except Exception:
                logger.exception("Ingestion queue recovery failed")
            last_recovery = now_monotonic

        client = _client()
        if client is None:
            time.sleep(2)
            continue

        try:
            item = client.brpop(QUEUE_NAME, timeout=5)
        except Exception:
            logger.exception("Redis worker read failed")
            time.sleep(2)
            continue

        if not item:
            continue

        _, job_id = item

        try:
            process_job(job_id)
        except Exception:
            # The processor is responsible for marking the job failed. This
            # guard prevents one unexpected exception from killing the worker.
            logger.exception("Unhandled ingestion worker error job=%s", job_id)
