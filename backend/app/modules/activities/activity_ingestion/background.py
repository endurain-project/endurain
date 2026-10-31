"""Owns the worker pool used when durable jobs are disabled.

When ``JOBS_ENABLED`` is off there is no durable-job worker to drain the queue,
so bulk import, uploads and refreshes fall back to a small thread pool that
processes the work in the background (:mod:`.dispatch_service` decides when). The pool
lives here so it has a single owner with an explicit lifecycle: the API lifespan
shuts it down.

It is a fallback, not a second implementation: both paths call the same job
bodies, so the only thing that varies is durability. Nothing here is used on the
durable-job path — see ``activity_ingestion.subscribers``.
"""

from collections.abc import Callable
from concurrent.futures import Future
from typing import Any

import core.local_pool as core_local_pool

# Deliberately small: ingestion is I/O plus CPU-heavy parsing, and the pool
# competes with the request threadpool on the same process.
_MAX_WORKERS = 2

# Jobs held at once, running and queued. Past it a request is refused before its job row is
# created, so a burst of uploads cannot queue work the process will take hours to reach.
_MAX_PENDING = 100

_pool = core_local_pool.BoundedPool("activity-ingestion", workers=_MAX_WORKERS, max_pending=_MAX_PENDING)


def require_capacity() -> None:
    """Refuse up front when the pool is full.

    Raises:
        PoolFullError: When the pool holds its limit of jobs.
    """
    _pool.require_capacity()


def submit(run: Callable[..., Any], *args: Any) -> Future:
    """Run a job body on the background pool.

    The body is passed in rather than imported here: the service owns the job
    bodies and imports this module, so importing it back would be a cycle.

    Args:
        run: The job body (``run_upload_job``, ``run_refresh_job``, ...).
        *args: Arguments for the job body.

    Returns:
        The scheduled future (a failure is logged when the job ends).

    Raises:
        PoolFullError: When the pool holds its limit of jobs.
    """
    return _pool.submit(run, *args)


def shutdown(wait: bool = False) -> None:
    """Shut the background pool down, if it was ever started.

    Called from the API lifespan. ``wait=False`` by default so shutdown is not
    blocked by a long-running import; in-flight files are lost either way when
    durable jobs are disabled, which is exactly the reliability gap durable jobs
    close.

    Args:
        wait: Whether to block until running tasks finish.
    """
    _pool.shutdown(wait=wait)
