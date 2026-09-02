"""Registry mapping a durable ``subscriber_id`` to its handler and event type.

A durable subscriber declares a stable id (independent of its Python module
path) and the event type it reacts to, and registers a handler here. The relay
uses the event-type mapping to fan an event out into one job per subscriber; the
worker uses the id mapping to resolve a claimed job back to its handler. The same
code therefore runs subscribers in-process or out-of-process in a worker.
"""

from collections import defaultdict
from collections.abc import Callable

from infra.events import Event

JobHandler = Callable[[Event], None]


class JobHandlerRegistry:
    """A process-local registry of durable subscribers."""

    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}
        self._by_event_type: dict[str, list[str]] = defaultdict(list)

    def register(self, event_type: str, subscriber_id: str, handler: JobHandler) -> None:
        """
        Register (or replace) a durable subscriber.

        Args:
            event_type: The domain-event channel the subscriber reacts to.
            subscriber_id: The stable durable-subscriber identifier.
            handler: The callable that processes an event for this subscriber.

        Returns:
            None.
        """
        self._handlers[subscriber_id] = handler
        if subscriber_id not in self._by_event_type[event_type]:
            self._by_event_type[event_type].append(subscriber_id)

    def get(self, subscriber_id: str) -> JobHandler | None:
        """
        Look up the handler for a subscriber id.

        Args:
            subscriber_id: The durable-subscriber identifier to resolve.

        Returns:
            The registered handler, or ``None`` when none is registered.
        """
        return self._handlers.get(subscriber_id)

    def subscribers_for(self, event_type: str) -> tuple[str, ...]:
        """
        Return the durable subscriber ids registered for an event type.

        Args:
            event_type: The domain-event channel to fan out.

        Returns:
            The subscriber ids, in registration order.
        """
        return tuple(self._by_event_type.get(event_type, ()))

    def subscriber_ids(self) -> frozenset[str]:
        """
        Return every registered subscriber id, across all event types.

        Args:
            None.

        Returns:
            The registered durable-subscriber ids.
        """
        return frozenset(self._handlers)

    def clear(self) -> None:
        """
        Remove every registration (used to reset state between tests).

        Args:
            None.

        Returns:
            None.
        """
        self._handlers.clear()
        self._by_event_type.clear()


# Process-wide default registry: durable subscribers register here at startup and
# the worker/relay resolve handlers and fan-out from it.
registry = JobHandlerRegistry()
