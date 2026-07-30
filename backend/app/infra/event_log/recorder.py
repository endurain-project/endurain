"""The event-log recorder — persists event lifecycle to the event_log table.

Implements the :class:`~infra.providers.EventRecorder` protocol. The
composition root injects one instance into the event bus when
``EVENT_LOG_ENABLED`` is set. Each write opens its own short-lived session and
swallows/logs any storage error, so a database hiccup never breaks event
processing — observability is best-effort by design.
"""

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

import core.logger as core_logger
import infra.event_log.crud as event_log_crud
from core.database import SessionLocal
from infra.events import Event

logger = core_logger.get_logger(__name__)


class EventLogRecorder:
    """Records event lifecycle transitions to the ``event_log`` table."""

    def record_published(self, event: Event) -> None:
        """
        Record the initial ``published`` row for an event.

        Args:
            event: The event envelope being published.

        Returns:
            None.
        """
        self._safely("record_published", lambda db: event_log_crud.record_published(event, db))

    def record_queued(self, event: Event) -> None:
        """
        Record a terminal ``queued`` row for an event routed to durable jobs.

        Args:
            event: The event envelope staged for durable delivery.

        Returns:
            None.
        """
        self._safely("record_queued", lambda db: event_log_crud.record_queued(event, db))

    @contextmanager
    def track(
        self,
        event: Event,
        *,
        worker_id: str,
        handler_name: str | None,
        record_processing: bool = True,
    ) -> Iterator[None]:
        """
        Record ``processing`` then ``completed`` / ``failed`` around handlers.

        Args:
            event: The event being processed.
            worker_id: The process/consumer handling the event.
            handler_name: The subscriber(s) that process the event.
            record_processing: Whether to write the intermediate ``processing``
                row. False for the synchronous in-process bus, where the row goes
                published -> completed within one call and the intermediate state
                is never observed — saving a database round-trip on the hot path.

        Yields:
            None — control returns to the caller to run the handlers.

        Raises:
            Exception: Re-raises any handler exception after recording failure.
        """
        if record_processing:
            self._safely(
                "mark_processing",
                lambda db: event_log_crud.mark_processing(event.event_id, worker_id, db),
            )
        start = time.monotonic()
        try:
            yield
        except Exception as error:
            error_message = str(error)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            self._safely(
                "mark_failed",
                lambda db: event_log_crud.mark_failed(event.event_id, handler_name, error_message, elapsed_ms, db),
            )
            raise
        elapsed_ms = int((time.monotonic() - start) * 1000)
        self._safely(
            "mark_completed",
            lambda db: event_log_crud.mark_completed(event.event_id, handler_name, elapsed_ms, db),
        )

    def _safely(self, operation: str, write: Callable[[Session], None]) -> None:
        """
        Run a recording write, swallowing and logging any storage error.

        Args:
            operation: Label for the write, used in the log message.
            write: Callable performing the write against a session.

        Returns:
            None.
        """
        try:
            with SessionLocal() as db:
                write(db)
        except Exception as error:  # observability must never break event processing
            logger.warning(f"event_log {operation} failed: {error!r}")
