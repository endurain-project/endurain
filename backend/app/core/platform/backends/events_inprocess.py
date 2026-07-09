"""In-process (synchronous) ``EventBusProvider`` backend."""

from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING

from core.platform.events import Event

if TYPE_CHECKING:
    from core.platform.providers import EventRecorder

# Worker label recorded for in-process dispatch (single process, no consumer).
_INPROCESS_WORKER = "inprocess"


class InProcessEventBus:
    """Synchronous ``EventBusProvider`` — ``publish`` runs subscribers inline.

    Correct for the ``local`` profile: dispatch is a direct function call in the
    same thread, and a handler exception propagates to the caller (the scheduler
    backfill is the safety net). ``start`` / ``stop`` are no-ops because there is
    no background consumer.

    When an :class:`~core.platform.providers.EventRecorder` is injected, each
    ``publish`` records the event's lifecycle (published -> processing ->
    completed/failed) around the inline dispatch; a handler exception is recorded
    as a failure and then re-raised, preserving the propagate-to-caller contract.
    """

    def __init__(self, recorder: "EventRecorder | None" = None) -> None:
        self._handlers: dict[str, list[Callable[[Event], None]]] = defaultdict(list)
        self._recorder = recorder

    def publish(self, event: Event) -> None:
        handlers = self._handlers.get(event.event_type, [])
        recorder = self._recorder
        if recorder is None:
            for handler in handlers:
                handler(event)
            return
        recorder.record_published(event)
        handler_name = ",".join(handler.__name__ for handler in handlers) or None
        with recorder.track(event, worker_id=_INPROCESS_WORKER, handler_name=handler_name):
            for handler in handlers:
                handler(event)

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        self._handlers[event_type].append(handler)

    def start(self) -> None:
        """No-op — in-process dispatch needs no consumer loop."""

    def stop(self) -> None:
        """No-op — in-process dispatch needs no consumer loop."""
