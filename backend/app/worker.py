import logging
import signal
import threading
import time

from .db import init_db
from .job_queue import start_worker, stop_worker
from .main import _run_queued_job

logger = logging.getLogger("deepsearch.worker")


def _shutdown(signum, _frame):
    logger.info("Received signal %s; stopping ingestion worker", signum)
    stop_worker()


def main():
    logging.basicConfig(level=logging.INFO)
    init_db()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    if not start_worker(_run_queued_job):
        raise RuntimeError(
            "Redis ingestion worker could not start. Check REDIS_URL and "
            "Render Key Value connectivity."
        )

    logger.info("DeepSearch background ingestion service is ready")

    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        _shutdown(signal.SIGINT, None)


if __name__ == "__main__":
    main()
