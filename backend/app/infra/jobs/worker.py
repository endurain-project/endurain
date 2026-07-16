"""The worker loop that drains the durable job queue.

``run_worker`` is the blocking claim/run loop used both by the standalone worker
entrypoint and by :class:`BackgroundWorker`, which runs it on a daemon thread so
a single-process (``local``) deployment can process durable jobs without a
separate container. Reaping expired leases is a scheduled job, not part of this
loop.
"""

import threading

import core.logger as core_logger
from infra.jobs.runner import JobRunner

_STOP_JOIN_TIMEOUT = 5.0


def run_worker(runner: JobRunner, *, poll_interval_seconds: float, stop: threading.Event) -> None:
    """
    Claim and process jobs until ``stop`` is set.

    Loops immediately while a batch found work (to drain a backlog) and waits
    ``poll_interval_seconds`` when the queue was empty. A failed iteration is
    logged and the loop continues.

    Args:
        runner: The job runner to drive.
        poll_interval_seconds: Idle wait between empty polls.
        stop: Event that ends the loop when set.

    Returns:
        None.
    """
    core_logger.print_to_log_and_console("Durable job worker started")
    while not stop.is_set():
        try:
            processed = runner.run_once()
        except Exception as error:
            core_logger.print_to_log("Durable job worker iteration failed", "error", exc=error)
            processed = 0
        if processed == 0:
            stop.wait(poll_interval_seconds)
    core_logger.print_to_log_and_console("Durable job worker stopped")


class BackgroundWorker:
    """Runs :func:`run_worker` on a daemon thread for in-process deployments."""

    def __init__(self, runner: JobRunner, *, poll_interval_seconds: float) -> None:
        self._runner = runner
        self._poll_interval_seconds = poll_interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """
        Start the worker thread (idempotent).

        Args:
            None.

        Returns:
            None.
        """
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=run_worker,
            args=(self._runner,),
            kwargs={"poll_interval_seconds": self._poll_interval_seconds, "stop": self._stop},
            name="durable-job-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """
        Signal the worker thread and wait briefly for it to finish.

        Args:
            None.

        Returns:
            None.
        """
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=_STOP_JOIN_TIMEOUT)
