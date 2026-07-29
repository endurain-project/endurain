"""Helpers for writing event-bus subscribers.

Every domain subscriber in the codebase is written twice: a raising core (the
durable-job handler, so the runner can retry and eventually dead-letter) and a
swallowing wrapper (the bus subscriber, so a derived-work failure never breaks
the producing request). :func:`best_effort` is that wrapper, defined once here
instead of being copy-pasted per subsystem — which previously meant each copy
could drift in what it logged and which exceptions it caught.
"""

import functools
from collections.abc import Callable

import core.logger as core_logger
from infra.events import META_ACTIVITY_ID, META_USER_ID, Event

logger = core_logger.get_logger(__name__)


def best_effort(handler: Callable[[Event], None]) -> Callable[[Event], None]:
    """Wrap a raising event handler into a swallowing bus subscriber.

    The returned subscriber logs and absorbs **any** exception, so derived work
    (thumbnails, geocoding, notifications, cleanup) can never fail the request or
    consumer that produced the event. The wrapped handler stays available for
    durable-job registration, where failures must propagate to drive retry and
    dead-lettering.

    Usage::

        def do_work_for_event(event: Event) -> None: ...

        on_event_do_work = best_effort(do_work_for_event)

    Args:
        handler: The raising handler to wrap.

    Returns:
        A subscriber with the same signature that never raises.
    """

    @functools.wraps(handler)
    def _subscriber(event: Event) -> None:
        try:
            handler(event)
        except Exception as err:
            logger.error(
                "Event subscriber failed",
                exc_info=err,
                extra=core_logger.context(
                    event_type=event.event_type,
                    event_id=event.event_id,
                    subscriber=handler.__name__,
                    activity_id=event.metadata.get(META_ACTIVITY_ID) or event.payload.get(META_ACTIVITY_ID),
                    user_id=event.metadata.get(META_USER_ID) or event.payload.get(META_USER_ID),
                ),
            )

    return _subscriber
