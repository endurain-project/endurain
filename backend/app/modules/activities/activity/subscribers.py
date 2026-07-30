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
import modules.activities.activity.events as activity_events
import modules.notifications.utils as notifications_utils
import modules.websocket.manager as websocket_manager
import modules.websocket.utils as websocket_utils
from infra.events import Event
from infra.jobs.registry import JobHandlerRegistry
from infra.providers import EventBusProvider

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
    payload = activity_events.ActivityCreatedPayload.model_validate(event.payload)

    with core_database.SessionLocal() as db:
        notification, ws_message = notifications_utils.create_activity_created_notification(
            payload.user_id,
            payload.activity_id,
            payload.duplicate_start_time,
            db,
        )

    # Best-effort websocket push on the main loop; the row above is the record,
    # so a failed/dropped push (offline client, no loop) is not an error.
    #
    # KNOWN LIMITATION (distributed): get_websocket_manager() is the PROCESS-LOCAL
    # connection registry, so this reaches only clients whose websocket is held by
    # THIS process. In a multi-replica deployment the durable job may run on a
    # worker/replica other than the one holding the user's socket, so the live push
    # is silently dropped for that client. No durable state is lost — the
    # notification ROW is written, so the client still sees it on its next fetch.
    # The real fix (cross-replica fan-out, e.g. a Redis pub/sub relay to every
    # replica's manager) belongs to the future websocket module rework; noted here
    # so it is not forgotten.
    platform_async_bridge.dispatch(
        websocket_utils.notify_frontend(
            payload.user_id,
            websocket_manager.get_websocket_manager(),
            {"message": ws_message, "notification_id": notification.id},
        )
    )


def on_activity_created_notify(event: Event) -> None:
    """Bus subscriber: create the new-activity notification, swallowing any error.

    Wraps :func:`notify_activity_created_for_event` so a notification failure
    never breaks activity import.

    Args:
        event: The ``activity.created`` event.

    Returns:
        None.
    """
    try:
        notify_activity_created_for_event(event)
    except Exception as err:
        core_logger.print_to_log(
            f"activity.created notification handler failed for activity {event.payload.get('activity_id')}: {err}",
            "error",
            exc=err,
        )


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
