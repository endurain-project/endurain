"""Event subscriber removing an activity's media files on deletion.

Mirrors the thumbnail and source-file cleanup subscribers: a durable
``*_for_event`` core that **raises** so the durable-job runner can retry, and an
``on_*`` bus subscriber that **swallows** so a cleanup failure never breaks
activity deletion.

Without this, deleting an activity removed its ``activity_media`` rows (they
cascade) but left the image files on disk forever — a storage leak, and a privacy
problem, since an athlete deleting an activity reasonably expects its photos to
go with it. Bulk paths (account deletion, unlinking a provider) publish the same
event, so they are covered too.

Cleanup is keyed on the activity id rather than the stored paths, because the
rows holding those paths are already gone by the time the event is handled.

There is deliberately no reconciliation net: like the sibling cleanups this is an
idempotent teardown keyed by activity id, and a stray orphaned file is harmless.
"""

import infra.event_versioning as platform_event_versioning
import modules.activities.activity.events as activity_events
import modules.activities.activity_media.service as activity_media_service
from infra.events import Event
from infra.jobs.registry import JobHandlerRegistry
from infra.providers import EventBusProvider
from infra.subscribers import best_effort

# Stable durable-subscriber id (independent of module path) so job history and
# dedup survive refactors.
ACTIVITY_MEDIA_CLEANUP_SUBSCRIBER_ID = "activity_media.cleanup"


def cleanup_activity_media_for_event(event: Event) -> None:
    """Delete a deleted activity's media files; raises on failure.

    The durable-job handler for ``activity.deleted``: errors propagate so the
    runner retries. Keyed by activity id, so the already-cascaded rows are not
    needed and the delete is idempotent.

    Args:
        event: The ``activity.deleted`` event (payload ``{"activity_id": int}``).

    Returns:
        None.
    """
    payload = platform_event_versioning.parse_payload(activity_events.ActivityDeletedPayload, event)
    activity_media_service.delete_media_files_for_activity(payload.activity_id)


# Bus subscriber: deletes a deleted activity's media files, swallowing errors so
# a cleanup failure never breaks activity deletion.
on_activity_deleted_cleanup_media = best_effort(cleanup_activity_media_for_event)


def register_activity_media_cleanup_subscribers(events: EventBusProvider) -> None:
    """Register the media cleanup subscriber for ``activity.deleted``.

    Called once at startup before the event bus is started.

    Args:
        events: The event-bus provider to subscribe on.

    Returns:
        None.
    """
    events.subscribe(activity_events.ACTIVITY_DELETED, on_activity_deleted_cleanup_media)


def register_activity_media_cleanup_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the media cleanup handler as a durable job subscriber.

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
        ACTIVITY_MEDIA_CLEANUP_SUBSCRIBER_ID,
        cleanup_activity_media_for_event,
    )
