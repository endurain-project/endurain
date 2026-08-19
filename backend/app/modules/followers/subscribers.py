"""Event subscribers wiring follower notifications to follow lifecycle events.

The follow relationship row is the source of truth; the notification (and its
best-effort websocket push) is a reaction to the ``follower.requested`` /
``follower.accepted`` events. Each subscriber writes the notification row
synchronously (safe on the bus consumer thread) and then dispatches a best-effort
websocket push onto the main event loop via :mod:`infra.async_bridge`.

Same two-shape convention as the activities subscribers: a ``*_for_event`` core
that **raises** for durable retries, and an
``on_*`` bus subscriber built with :func:`infra.subscribers.best_effort` that
swallows so a notification problem never breaks the follow itself.
"""

import core.database as core_database
import core.logger as core_logger
import infra.async_bridge as platform_async_bridge
import infra.event_versioning as platform_event_versioning
import modules.followers.events as followers_events
import modules.notifications.integration_service as notifications_integration
import modules.websocket.integration_service as websocket_integration
from infra.events import Event
from infra.jobs.registry import JobHandlerRegistry
from infra.providers import EventBusProvider
from infra.subscribers import best_effort

logger = core_logger.get_logger(__name__)

FOLLOWER_REQUESTED_NOTIFICATION_SUBSCRIBER_ID = "followers.notify_requested"
FOLLOWER_ACCEPTED_NOTIFICATION_SUBSCRIBER_ID = "followers.notify_accepted"


def notify_follower_requested_for_event(event: Event) -> None:
    """Notify the target of a new follow request; raises on failure.

    Writes the notification row for the target user and dispatches a best-effort
    websocket push onto the main loop.

    Args:
        event: The ``follower.requested`` event (payload
            ``{"requester_user_id": int, "target_user_id": int}``).

    Returns:
        None.
    """
    payload = platform_event_versioning.parse_payload(followers_events.FollowerRequestedPayload, event)
    with core_database.SessionLocal() as db:
        notification, ws_message = notifications_integration.create_follow_request_notification(
            payload.requester_user_id, payload.target_user_id, db
        )
    # Best-effort websocket push to the notified user on the main loop; the row
    # above is the record, so a dropped push (offline client, no loop) is fine.
    platform_async_bridge.dispatch(
        websocket_integration.push_to_user(
            payload.target_user_id,
            {"message": ws_message, "notification_id": notification.id},
        )
    )
    logger.debug(
        "Created follow-request notification",
        extra=core_logger.context(
            requester_user_id=payload.requester_user_id,
            target_user_id=payload.target_user_id,
            notification_id=notification.id,
        ),
    )


def notify_follower_accepted_for_event(event: Event) -> None:
    """Notify the requester that their request was accepted; raises on failure.

    Writes the notification row for the original requester and dispatches a
    best-effort websocket push onto the main loop.

    Args:
        event: The ``follower.accepted`` event (payload
            ``{"accepter_user_id": int, "requester_user_id": int}``).

    Returns:
        None.
    """
    payload = platform_event_versioning.parse_payload(followers_events.FollowerAcceptedPayload, event)
    with core_database.SessionLocal() as db:
        notification, ws_message = notifications_integration.create_follow_accepted_notification(
            payload.accepter_user_id, payload.requester_user_id, db
        )
    platform_async_bridge.dispatch(
        websocket_integration.push_to_user(
            payload.requester_user_id,
            {"message": ws_message, "notification_id": notification.id},
        )
    )
    logger.debug(
        "Created follow-accepted notification",
        extra=core_logger.context(
            accepter_user_id=payload.accepter_user_id,
            requester_user_id=payload.requester_user_id,
            notification_id=notification.id,
        ),
    )


# Bus subscribers: notify, swallowing any error so a notification failure never
# breaks the follow request/acceptance itself (the relationship row is committed).
on_follower_requested_notify = best_effort(notify_follower_requested_for_event)
on_follower_accepted_notify = best_effort(notify_follower_accepted_for_event)


def register_follower_notification_subscribers(events: EventBusProvider) -> None:
    """Register the follower-notification subscribers on the running bus.

    Called once at startup (the API lifespan) before the event bus is started.
    On the in-process bus these run inline; on the Redis-Streams bus a consumer
    runs them at-least-once.

    Args:
        events: The event-bus provider to subscribe the handlers on.

    Returns:
        None.
    """
    events.subscribe(followers_events.FOLLOWER_REQUESTED, on_follower_requested_notify)
    events.subscribe(followers_events.FOLLOWER_ACCEPTED, on_follower_accepted_notify)


def register_follower_notification_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register retryable follower-notification handlers for outbox delivery."""
    registry.register(
        followers_events.FOLLOWER_REQUESTED,
        FOLLOWER_REQUESTED_NOTIFICATION_SUBSCRIBER_ID,
        notify_follower_requested_for_event,
    )
    registry.register(
        followers_events.FOLLOWER_ACCEPTED,
        FOLLOWER_ACCEPTED_NOTIFICATION_SUBSCRIBER_ID,
        notify_follower_accepted_for_event,
    )
