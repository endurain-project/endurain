"""Owns the background worker pool used when durable jobs are disabled.

When ``JOBS_ENABLED`` is off there is no durable-job worker to drain the queue,
so bulk import, uploads and refreshes fall back to a small thread pool that
processes the work in the background (:mod:`.dispatch_service` decides when). That pool lives here rather than at module
scope in the router so it has a single owner with an explicit lifecycle: the API
lifespan shuts it down, instead of it being leaked on exit as an unreferenced
module global.

It is a fallback, not a second implementation: both paths call the same job
bodies, so the only thing that varies is durability. Nothing here is used on the
durable-job path — see ``activity_ingestion.subscribers``.
"""

import contextvars
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

import core.logger as core_logger

logger = core_logger.get_logger(__name__)

# Deliberately small: ingestion is I/O plus CPU-heavy parsing, and the pool
# competes with the request threadpool on the same process.
_MAX_WORKERS = 2

_executor: ThreadPoolExecutor | None = None


def _get_executor() -> ThreadPoolExecutor:
    """Return the shared ingestion executor, creating it on first use.

    Lazily created so an install running with durable jobs enabled never spawns
    threads it will not use.

    Returns:
        The process-wide ingestion thread pool.
    """
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="activity-ingestion")
    return _executor


def _log_failure(future: Future) -> None:
    """Log an exception raised by a background ingestion task.

    Without this the exception would be swallowed by the future and the work
    would appear to have completed.

    Args:
        future: The completed future to inspect.
    """
    exc = future.exception()
    if isinstance(exc, Exception):
        logger.error("Background ingestion task failed", exc_info=exc)


def submit(run: Callable[..., Any], *args: Any) -> Future:
    """Run a job body on the background pool.

    The body is passed in rather than imported here: the service owns the job
    bodies and imports this module, so importing it back would be a cycle.

    Args:
        run: The job body (``run_upload_job``, ``run_refresh_job``, ...).
        *args: Arguments for the job body.

    Returns:
        The scheduled future (failures are logged via a done-callback).
    """
    logger.debug("Queued an ingestion job on the background pool", extra=core_logger.context(job=run.__name__))
    # Run under the caller's context so the request id reaches the job's logs.
    future = _get_executor().submit(contextvars.copy_context().run, run, *args)
    future.add_done_callback(_log_failure)
    return future


def shutdown(wait: bool = False) -> None:
    """Shut the background pool down, if it was ever started.

    Called from the API lifespan. ``wait=False`` by default so shutdown is not
    blocked by a long-running import; in-flight files are lost either way when
    durable jobs are disabled, which is exactly the reliability gap durable jobs
    close.

    Args:
        wait: Whether to block until running tasks finish.
    """
    global _executor
    if _executor is None:
        return
    logger.debug("Shutting down the ingestion background pool")
    _executor.shutdown(wait=wait, cancel_futures=True)
    _executor = None
