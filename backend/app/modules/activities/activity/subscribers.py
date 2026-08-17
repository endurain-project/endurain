"""Event subscribers wiring activity notifications to activity lifecycle events.

Mirrors the thumbnail subscriber pattern: a durable
``*_for_event`` core that **raises** so the durable-job runner can retry and
eventually dead-letter, and an ``on_*`` bus subscriber that **swallows** so a
notification failure never breaks activity import. The notification row is the
record; the websocket push is best-effort and is dispatched onto the main event
loop via :mod:`infra.async_bridge` (the subscriber itself runs synchronously,
possibly on a job-worker thread).

There is deliberately no reconciliation net here: a missed new-activity
notification is transient UI signal, not durable state (the activity row itself
is the source of truth), so — unlike the thumbnail backfill — there is nothing to
reconcile after the fact.
"""

import core.database as core_database
import core.logger as core_logger
import infra.async_bridge as platform_async_bridge
import infra.event_versioning as platform_event_versioning
import modules.activities.activity.events as activity_events
import modules.notifications.integration_service as notifications_integration
import modules.websocket.integration_service as websocket_integration
from infra.events import Event
from infra.jobs.registry import JobHandlerRegistry
from infra.providers import EventBusProvider
from infra.subscribers import best_effort

logger = core_logger.get_logger(__name__)

# Stable durable-subscriber id (independent of module path) so job history and
# dedup survive refactors.
ACTIVITY_NOTIFICATION_SUBSCRIBER_ID = "activity.notify_created"


def notify_activity_created_for_event(event: Event) -> None:
    """Create the new-activity notification for a created activity; raises on failure.

    The durable-job handler for ``activity.created``: any error propagates so the
    runner retries and eventually dead-letters the job. Writes the notification
    row and then dispatches a best-effort websocket push onto the main loop.

    Args:
        event: The ``activity.created`` event (payload
            ``{"activity_id": int, "user_id": int, "duplicate_start_time": bool}``).

    Returns:
        None.
    """
    payload = platform_event_versioning.parse_payload(activity_events.ActivityCreatedPayload, event)

    with core_database.SessionLocal() as db:
        notification, ws_message = notifications_integration.create_activity_created_notification(
            payload.user_id,
            payload.activity_id,
            payload.duplicate_start_time,
            db,
        )

    # Best-effort websocket push on the main loop; the row above is the record,
    # so a failed/dropped push (offline client, no loop) is not an error.
    #
    # KNOWN LIMITATION (distributed): the websocket registry is PROCESS-LOCAL, so
    # this reaches only clients whose websocket is held by THIS process. In a
    # multi-replica deployment the durable job may run on a worker/replica other
    # than the one holding the user's socket, so the live push is silently
    # dropped for that client. No durable state is lost — the notification ROW is
    # written, so the client still sees it on its next fetch. The real fix
    # (cross-replica fan-out) belongs to the websocket module rework.
    platform_async_bridge.dispatch(
        websocket_integration.push_to_user(
            payload.user_id,
            {"message": ws_message, "notification_id": notification.id},
        )
    )
    logger.debug(
        "Created new-activity notification",
        extra=core_logger.context(
            activity_id=payload.activity_id,
            user_id=payload.user_id,
            notification_id=notification.id,
        ),
    )


# Bus subscriber: creates the new-activity notification, swallowing any error so a
# notification failure never breaks activity import.
on_activity_created_notify = best_effort(notify_activity_created_for_event)


def register_activity_notification_subscribers(events: EventBusProvider) -> None:
    """Register the activity-notification subscriber for ``activity.created``.

    Called once at startup before the event bus is started.

    Args:
        events: The event-bus provider to subscribe on.

    Returns:
        None.
    """
    events.subscribe(activity_events.ACTIVITY_CREATED, on_activity_created_notify)


def register_activity_notification_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the activity-notification handler as a durable job subscriber.

    Used when durable jobs are enabled: the outbox relay fans ``activity.created``
    out into a retryable job keyed by this subscriber id, and the worker resolves
    it back to the raising ``*_for_event`` core.

    Args:
        registry: The durable-subscriber registry to register on.

    Returns:
        None.
    """
    registry.register(
        activity_events.ACTIVITY_CREATED,
        ACTIVITY_NOTIFICATION_SUBSCRIBER_ID,
        notify_activity_created_for_event,
    )
