"""Bridge for dispatching async work onto the main event loop from sync code.

Synchronous code cannot ``await``. Two situations in this backend need to run
genuinely async I/O from a synchronous context:

* a synchronous FastAPI route, which Starlette runs on a threadpool worker thread
  (no running event loop of its own), and
* an in-process event-bus subscriber, which runs inline on whatever thread called
  ``publish`` (a request thread, the scheduler, or a durable-job worker).

When such code must perform async I/O — pushing a websocket message is the
motivating case — it hands the coroutine to :func:`dispatch`, which schedules it
on the **main** event loop captured at application startup via
:func:`asyncio.run_coroutine_threadsafe`. This keeps the async work on the one
loop that owns the resources (e.g. the websocket connections) while letting the
producing code stay fully synchronous.

The main loop is a process-wide handle, so it lives in a module-level slot set
once from the lifespan startup and cleared on shutdown. This module imports
nothing from the domain layer or the platform substrate, so it is safe for any
module to depend on.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from concurrent.futures import Future
from typing import Any

import core.logger as core_logger

logger = core_logger.get_logger(__name__)

_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    """Record (or clear) the main event loop.

    Called once from the lifespan startup with the running loop, and again on
    shutdown with ``None``.

    Args:
        loop: The running main event loop, or ``None`` to clear it.

    Returns:
        None.
    """
    global _main_loop  # single process-wide handle, set once at startup
    _main_loop = loop


def capture_running_loop() -> None:
    """Capture the currently running loop as the main loop.

    Convenience for the lifespan startup: keeps the ``asyncio`` detail here rather
    than in ``main``. Must be called from within a running event loop.

    Returns:
        None.
    """
    set_main_loop(asyncio.get_running_loop())


def get_main_loop() -> asyncio.AbstractEventLoop | None:
    """Return the captured main event loop, or ``None`` if it is not set.

    Returns:
        The main event loop when the application is running, else ``None``
        (e.g. in unit tests, or before startup / after shutdown).
    """
    return _main_loop


def dispatch(coro: Coroutine[Any, Any, Any]) -> Future[Any] | None:
    """Schedule ``coro`` on the main event loop from any thread; fire-and-forget.

    Thread-safe. Intended for synchronous callers (sync routes, in-process
    subscribers) that need to run async I/O without awaiting it. Failures raised
    by the coroutine are logged (never surfaced to the caller), so a delivery
    failure — e.g. a dropped websocket — cannot break the synchronous work that
    triggered it.

    Args:
        coro: The coroutine to run on the main loop.

    Returns:
        The :class:`concurrent.futures.Future` tracking the scheduled coroutine,
        or ``None`` when no running main loop is available. In the ``None`` case
        the coroutine is closed so it does not emit a "coroutine was never
        awaited" warning.
    """
    loop = _main_loop
    if loop is None or loop.is_closed():
        logger.warning("async_bridge.dispatch called with no running main loop; dropping coroutine")
        coro.close()
        return None

    future = asyncio.run_coroutine_threadsafe(coro, loop)

    def _log_failure(completed: Future[Any]) -> None:
        # Runs on the loop thread once the coroutine finishes. Surface any error
        # to the log; a cancelled future has no exception to report.
        if completed.cancelled():
            return
        error = completed.exception()
        if error is None:
            return
        logger.error(
            f"async_bridge dispatched coroutine failed: {type(error).__name__}",
            exc_info=error if isinstance(error, Exception) else None,
        )

    future.add_done_callback(_log_failure)
    return future
