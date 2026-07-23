"""Event subscriber removing an activity's retained source file on deletion.

Mirrors the thumbnail cleanup subscriber: a durable ``*_for_event`` core that
**raises** so the durable-job runner can retry, and an ``on_*`` bus subscriber
that **swallows** so a cleanup failure never breaks activity deletion. The
storage key is derived from the activity id, so the already-deleted row is not
needed and the delete is idempotent (safe when no file was ever retained).

There is deliberately no reconciliation net: like thumbnail cleanup this is an
idempotent teardown keyed by activity id, and a stray orphaned file is harmless.
"""

import core.logger as core_logger
import infra.runtime as platform_runtime
import modules.activities.activity.events as activity_events
import modules.activities.activity_file_storage.service as activity_file_storage_service
from infra.events import Event
from infra.jobs.registry import JobHandlerRegistry
from infra.providers import EventBusProvider

# Stable durable-subscriber id (independent of module path) so job history and
# dedup survive refactors.
ACTIVITY_FILE_CLEANUP_SUBSCRIBER_ID = "activity_file_storage.cleanup"


def cleanup_activity_file_for_event(event: Event) -> None:
    """Delete a deleted activity's retained source file; raises on failure.

    The durable-job handler for ``activity.deleted``: errors propagate so the
    runner retries. The storage key is derived from the activity id, so the
    already-deleted row is not needed, and the delete is idempotent.

    Args:
        event: The ``activity.deleted`` event (payload ``{"activity_id": int}``).

    Returns:
        None.
    """
    activity_id = event.payload.get("activity_id")
    if not isinstance(activity_id, int):
        return
    storage = platform_runtime.get_active_platform().storage
    activity_file_storage_service.delete_activity_file(activity_id, storage)


def on_activity_deleted_cleanup_file(event: Event) -> None:
    """Bus subscriber: delete a deleted activity's source file, swallowing errors.

    Wraps :func:`cleanup_activity_file_for_event` so a cleanup failure never
    breaks activity deletion.

    Args:
        event: The ``activity.deleted`` event.

    Returns:
        None.
    """
    try:
        cleanup_activity_file_for_event(event)
    except Exception as err:
        core_logger.print_to_log(
            f"activity.deleted source-file cleanup failed for activity {event.payload.get('activity_id')}: {err}",
            "error",
            exc=err,
        )


def register_activity_file_cleanup_subscribers(events: EventBusProvider) -> None:
    """Register the source-file cleanup subscriber for ``activity.deleted``.

    Called once at startup before the event bus is started.

    Args:
        events: The event-bus provider to subscribe on.

    Returns:
        None.
    """
    events.subscribe(activity_events.ACTIVITY_DELETED, on_activity_deleted_cleanup_file)


def register_activity_file_cleanup_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the source-file cleanup handler as a durable job subscriber.

    Used when durable jobs are enabled: the outbox relay fans ``activity.deleted``
    out into a job keyed by this subscriber id, and the worker resolves it back to
    the raising ``*_for_event`` core.

    Args:
        registry: The durable-subscriber registry to register on.

    Returns:
        None.
    """
    registry.register(
        activity_events.ACTIVITY_DELETED,
        ACTIVITY_FILE_CLEANUP_SUBSCRIBER_ID,
        cleanup_activity_file_for_event,
    )
