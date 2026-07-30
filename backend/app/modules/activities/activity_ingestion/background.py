"""Owns the background worker pool used when durable jobs are disabled.

When ``JOBS_ENABLED`` is off there is no durable-job worker to drain the queue,
so bulk import and single-file uploads fall back to a small thread pool that
processes the work in the background. That pool lives here rather than at module
scope in the router so it has a single owner with an explicit lifecycle: the API
lifespan shuts it down, instead of it being leaked on exit as an unreferenced
module global.

It is a fallback, not a second implementation: both paths call the same job
bodies, so the only thing that varies is durability. Nothing here is used on the
durable-job path — see ``activity_ingestion.bulk_import_subscribers`` and
``activity_ingestion.upload_subscribers``.
"""

from concurrent.futures import Future, ThreadPoolExecutor

import core.logger as core_logger
import modules.activities.activity_ingestion.bulk_entry as bulk_entry

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

    Returns:
        None.
    """
    exc = future.exception()
    if isinstance(exc, Exception):
        logger.error("Background ingestion task failed", exc_info=exc)


def submit_bulk_import(user_id: int, file_paths: list[str], import_initiated_time: str) -> Future:
    """Process a batch of bulk-import files on the background pool.

    Args:
        user_id: The user the imported activities belong to.
        file_paths: Validated files to import, in order.
        import_initiated_time: ISO timestamp recorded on each imported activity.

    Returns:
        The scheduled future (failures are logged via a done-callback).
    """
    logger.info(
        "Queued bulk import batch on the background pool",
        extra=core_logger.context(user_id=user_id, file_count=len(file_paths)),
    )
    future = _get_executor().submit(
        bulk_entry.process_all_files_sync,
        user_id,
        file_paths,
        import_initiated_time=import_initiated_time,
    )
    future.add_done_callback(_log_failure)
    return future


def submit_upload(job_id: str) -> Future:
    """Import one staged upload on the background pool.

    Args:
        job_id: The ``activity_upload_jobs`` row to process.

    Returns:
        The scheduled future (failures are logged via a done-callback).
    """
    # Imported here, not at module scope: ``upload_jobs`` owns the choice between
    # this pool and the durable worker, so it imports this module. Deferring the
    # import keeps the dependency one-way at module load.
    import modules.activities.activity_ingestion.upload_jobs as upload_jobs

    logger.info(
        "Queued an activity upload on the background pool",
        extra=core_logger.context(job_id=job_id),
    )
    future = _get_executor().submit(upload_jobs.run_upload_job, job_id)
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

    Returns:
        None.
    """
    global _executor
    if _executor is None:
        return
    logger.debug("Shutting down the ingestion background pool")
    _executor.shutdown(wait=wait, cancel_futures=True)
    _executor = None
