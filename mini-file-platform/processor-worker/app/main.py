from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

# Allow running directly (python -m app.main) outside the virtualenv context.
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from shared.utils.log_config import get_logger

from app.consumer import consume_one

log = get_logger(__name__)
_running = True


def _handle_signal(signum, frame) -> None:
    global _running
    _running = False
    log.info("shutdown signal received", extra={"signal": signum})


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    queue_url = os.environ["SQS_FILE_JOBS_URL"]
    log.info("processor-worker started", extra={"queue_url": queue_url})

    while _running:
        try:
            consume_one(queue_url)
        except Exception as exc:
            log.error("unhandled loop error", extra={"error": str(exc)}, exc_info=True)
            time.sleep(5)

    log.info("processor-worker stopped")


if __name__ == "__main__":
    main()
