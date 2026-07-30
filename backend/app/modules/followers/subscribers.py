"""Event subscribers wiring follower notifications to follow lifecycle events.

The follow relationship row is the source of truth; the notification (and its
best-effort websocket push) is a reaction to the ``follower.requested`` /
``follower.accepted`` events. Each subscriber writes the notification row
synchronously (safe on the bus consumer thread) and then dispatches a best-effort
websocket push onto the main event loop via :mod:`infra.async_bridge`.

Same two-shape convention as the activities subscribers: a ``*_for_event`` core
that **raises** (so it could be registered as a durable handler unchanged), and an
``on_*`` bus subscriber built with :func:`infra.subscribers.best_effort` that
swallows so a notification problem never breaks the follow itself.

These are **bus subscribers only** (no durable-job handlers). A follow
notification is transient UI signal, not durable derived state: if delivery is
dropped, the follow relationship row still exists, so the target simply sees the
pending/accepted state on their next fetch. There is nothing to reconcile after
the fact, so — unlike the activities thumbnail/geocoding subscribers — no durable
job or reconciliation net is warranted.
"""

import core.database as core_database
import infra.async_bridge as platform_async_bridge
import modules.followers.events as followers_events
import modules.notifications.utils as notifications_utils
import modules.websocket.manager as websocket_manager
import modules.websocket.utils as websocket_utils
from infra.events import Event
from infra.providers import EventBusProvider
from infra.subscribers import best_effort


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
    payload = followers_events.FollowerRequestedPayload.model_validate(event.payload)
    with core_database.SessionLocal() as db:
        notification, ws_message = notifications_utils.create_new_follower_request_notification(
            payload.requester_user_id, payload.target_user_id, db
        )
    # Best-effort websocket push to the notified user on the main loop; the row
    # above is the record, so a dropped push (offline client, no loop) is fine.
    platform_async_bridge.dispatch(
        websocket_utils.notify_frontend(
            payload.target_user_id,
            websocket_manager.get_websocket_manager(),
            {"message": ws_message, "notification_id": notification.id},
        )
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
    payload = followers_events.FollowerAcceptedPayload.model_validate(event.payload)
    with core_database.SessionLocal() as db:
        notification, ws_message = notifications_utils.create_accepted_follower_request_notification(
            payload.accepter_user_id, payload.requester_user_id, db
        )
    platform_async_bridge.dispatch(
        websocket_utils.notify_frontend(
            payload.requester_user_id,
            websocket_manager.get_websocket_manager(),
            {"message": ws_message, "notification_id": notification.id},
        )
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
