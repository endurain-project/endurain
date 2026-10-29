"""A bounded in-process thread pool for work that has no durable worker to run it.

Without durable jobs, background work runs on threads of the API process. An unbounded queue
lets a burst of work, or a few long jobs, hold every thread while the queue behind them grows
without limit. This pool counts the jobs it holds, running and queued, and refuses a job past that
bound so the caller can answer or drop it instead of queueing it indefinitely.
"""

import contextvars
import functools
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

import core.exceptions as core_exceptions
import core.logger as core_logger

logger = core_logger.get_logger(__name__)


class PoolFullError(core_exceptions.ServiceUnavailableError):
    """Raised when a pool already holds its limit of jobs."""


class BoundedPool:
    """Thread pool that holds at most ``max_pending`` jobs, running and queued together.

    Jobs run under the submitter's ``contextvars`` context, so the request id reaches their logs.
    The threads start on the first job, and :meth:`shutdown` lets a later job start them again.

    Attributes:
        name: Names the pool's threads and its log lines.
    """

    def __init__(self, name: str, *, workers: int, max_pending: int) -> None:
        """Create a pool; no thread starts until the first job.

        Args:
            name: Thread name prefix and label in log lines and the full-pool error.
            workers: Jobs that run at the same time.
            max_pending: Jobs held at once, running and queued; at least ``workers``.
        """
        self.name = name
        self._workers = workers
        self._max_pending = max_pending
        self._pending = 0
        self._executor: ThreadPoolExecutor | None = None
        self._changed = threading.Condition()

    def has_capacity(self) -> bool:
        """Report whether a job would be accepted now.

        Advisory: another thread may take the slot before the caller submits.

        Returns:
            True when fewer than ``max_pending`` jobs are held.
        """
        with self._changed:
            return self._pending < self._max_pending

    def require_capacity(self) -> None:
        """Refuse up front when the pool holds its limit, so a caller can answer before it commits to a job.

        Advisory, like :meth:`has_capacity`; :meth:`submit` is the check that holds.

        Raises:
            PoolFullError: When the pool holds ``max_pending`` jobs.
        """
        if not self.has_capacity():
            raise PoolFullError(f"Too many {self.name} jobs in progress; try again shortly")

    def submit(self, run: Callable[..., Any], *args: Any, wait_seconds: float = 0, **kwargs: Any) -> Future:
        """Run a job on the pool, or refuse it when the pool holds its limit.

        Args:
            run: The job body.
            *args: Arguments for the job body.
            wait_seconds: How long to wait for a slot when the pool is full; ``0`` refuses at once.
            **kwargs: Keyword arguments for the job body.

        Returns:
            The job's future. A failure is logged when the job ends, so nobody has to read it.

        Raises:
            PoolFullError: When the pool still holds ``max_pending`` jobs after the wait.
        """
        with self._changed:
            if not self._changed.wait_for(lambda: self._pending < self._max_pending, timeout=wait_seconds):
                raise PoolFullError(f"Too many {self.name} jobs in progress; try again shortly")
            self._pending += 1
            executor = self._executor
            if executor is None:
                executor = self._executor = ThreadPoolExecutor(max_workers=self._workers, thread_name_prefix=self.name)
        try:
            future = executor.submit(contextvars.copy_context().run, run, *args, **kwargs)
        except BaseException:
            self._release()
            raise
        future.add_done_callback(functools.partial(self._finished, getattr(run, "__name__", repr(run))))
        return future

    def shutdown(self, *, wait: bool = False) -> None:
        """Stop accepting jobs and release the threads.

        Args:
            wait: Whether to wait for jobs still running; queued jobs are dropped either way.
        """
        with self._changed:
            executor, self._executor = self._executor, None
        if executor is not None:
            executor.shutdown(wait=wait, cancel_futures=True)

    def _release(self) -> None:
        """Give a slot back and wake a submitter waiting for one."""
        with self._changed:
            self._pending -= 1
            self._changed.notify()

    def _finished(self, job: str, future: Future) -> None:
        """Give the job's slot back and log an exception that escaped it.

        Args:
            job: The job body's name, for the log line.
            future: The finished job.
        """
        self._release()
        if future.cancelled():
            return
        error = future.exception()
        if error is not None:
            logger.error(
                "A <pool> job failed: <job>", exc_info=error, extra=core_logger.context(pool=self.name, job=job)
            )
