"""Event subscribers wiring the thumbnail subsystem to activity lifecycle events.

Registered once at startup (before the event bus starts). In the ``local``
profile the in-process bus runs these inline, synchronously, before the
producing request returns — behaviourally identical to inline generation; in a
``distributed`` profile a Redis-Streams consumer runs them later, at-least-once,
against object storage.

Two shapes of handler live here. The ``*_for_event`` cores **raise** on failure
so the durable-job runner can retry and eventually dead-letter them (used when
durable jobs are enabled). The ``on_*`` bus subscribers wrap those cores and
**swallow** errors so a thumbnail failure never breaks activity import or
deletion (used on the best-effort bus path). Either way the scheduled backfill
(:func:`service.generate_missing_activity_thumbnails`) is the safety net for the
create path.
"""

import jasil.event_versioning as platform_event_versioning
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider
from jasil.subscribers import best_effort

import core.database as core_database
import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.activities.activity.events as activity_events
import modules.activities.activity_thumbnail.scheduled_jobs as activity_thumbnail_scheduled_jobs
import modules.activities.activity_thumbnail.service as activity_thumbnail_service
import modules.server_settings.events as server_settings_events

logger = core_logger.get_logger(__name__)

# Stable durable-subscriber ids (independent of module path) so job history and
# dedup survive refactors.
THUMBNAIL_GENERATE_SUBSCRIBER_ID = "activity_thumbnail.generate"
THUMBNAIL_CLEANUP_SUBSCRIBER_ID = "activity_thumbnail.cleanup"
THUMBNAIL_SETTINGS_CHANGED_SUBSCRIBER_ID = "activity_thumbnail.settings_changed"


def generate_activity_thumbnail_for_event(event: Event) -> None:
    """Generate a map thumbnail for a newly created activity; raises on failure.

    The durable-job handler for ``activity.created``: any error propagates so the
    runner retries and eventually dead-letters the job. No-ops for activities
    without at least two GPS waypoints (non-GPS activities cost nothing).

    Args:
        event: The ``activity.created`` event (payload
            ``{"activity_id": int, "user_id": int}``).
    """
    payload = platform_event_versioning.parse_payload(activity_events.ActivityCreatedPayload, event)
    storage = platform_runtime.get_active_platform().storage
    with core_database.SessionLocal() as db:
        key = activity_thumbnail_service.generate_thumbnail_for_activity(
            payload.activity_id, payload.user_id, storage, db
        )
    logger.debug(
        "Handled activity.created for thumbnails",
        extra=core_logger.context(activity_id=payload.activity_id, stored=key is not None),
    )


# Bus subscriber: generates a map thumbnail, swallowing any error so a thumbnail
# failure never breaks activity import (the hourly backfill regenerates any missed).
on_activity_created_generate_thumbnail = best_effort(generate_activity_thumbnail_for_event)


def cleanup_activity_thumbnail_for_event(event: Event) -> None:
    """Delete a deleted activity's stored thumbnail; raises on failure.

    The durable-job handler for ``activity.deleted``: errors propagate so the
    runner retries. The storage key is derived from the activity ID, so the
    already-deleted row is not needed, and the delete is idempotent (safe when no
    thumbnail ever existed).

    Args:
        event: The ``activity.deleted`` event (payload ``{"activity_id": int}``).
    """
    payload = platform_event_versioning.parse_payload(activity_events.ActivityDeletedPayload, event)
    storage = platform_runtime.get_active_platform().storage
    activity_thumbnail_service.delete_activity_thumbnail(payload.activity_id, storage)
    logger.debug(
        "Deleted thumbnail for deleted activity",
        extra=core_logger.context(activity_id=payload.activity_id),
    )


# Bus subscriber: deletes a deleted activity's thumbnail, swallowing any error so
# a cleanup failure never breaks activity deletion.
on_activity_deleted_cleanup_thumbnail = best_effort(cleanup_activity_thumbnail_for_event)


def _schedule_thumbnail_regeneration() -> None:
    """Run a delete-and-regenerate pass over every thumbnail, off the request path.

    Queued on the scheduler when this process runs one. A dedicated worker
    (``APP_ROLE=worker``) does not: a one-shot queued there is accepted and never
    runs. There the handler is already on a worker thread, so the pass runs inline.
    """
    if core_scheduler.scheduler.running:
        core_scheduler.run_once(
            activity_thumbnail_scheduled_jobs.regenerate_all_thumbnails,
            job_id="endurain_regenerate_all_thumbnails",
            description="thumbnail regeneration",
        )
        return
    # The job runner renews the lease while this runs and the backfill lock keeps
    # a requeued copy from repeating the delete phase; a pass past
    # ``jobs.max_runtime_seconds`` stops at its next ``lease_lost()`` check.
    logger.debug("Thumbnail regeneration: no scheduler in this process; running it inline")
    activity_thumbnail_scheduled_jobs.regenerate_all_thumbnails()


def regenerate_thumbnails_for_tile_settings_event(event: Event) -> None:
    """Queue thumbnail regeneration when changed settings request it.

    Args:
        event: The settings-changed event.
    """
    payload = platform_event_versioning.parse_payload(server_settings_events.TileSettingsChangedPayload, event)
    if not payload.regenerate_thumbnails:
        logger.debug(
            "Skipping thumbnail regeneration for tile settings change",
            extra=core_logger.context(changed_fields=payload.changed_fields),
        )
        return
    _schedule_thumbnail_regeneration()
    logger.debug(
        "Queued thumbnail regeneration for tile settings change",
        extra=core_logger.context(changed_fields=payload.changed_fields),
    )


on_tile_settings_changed_regenerate = best_effort(regenerate_thumbnails_for_tile_settings_event)


def register_thumbnail_subscribers(events: EventBusProvider) -> None:
    """Register the thumbnail subscribers for the activity lifecycle events.

    Called once at startup before the event bus is started.

    Args:
        events: The event-bus provider to subscribe on.
    """
    events.subscribe(activity_events.ACTIVITY_CREATED, on_activity_created_generate_thumbnail)
    events.subscribe(activity_events.ACTIVITY_DELETED, on_activity_deleted_cleanup_thumbnail)
    events.subscribe(server_settings_events.TILE_SETTINGS_CHANGED, on_tile_settings_changed_regenerate)


def register_thumbnail_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the thumbnail handlers as durable job subscribers.

    Used when durable jobs are enabled: the outbox relay fans ``activity.created``
    / ``activity.deleted`` out into jobs keyed by these subscriber ids, and the
    worker resolves them back to the raising ``*_for_event`` cores (so failures
    are retried and eventually dead-lettered).

    Args:
        registry: The durable-subscriber registry to register on.
    """
    registry.register(
        activity_events.ACTIVITY_CREATED,
        THUMBNAIL_GENERATE_SUBSCRIBER_ID,
        generate_activity_thumbnail_for_event,
    )
    registry.register(
        activity_events.ACTIVITY_DELETED,
        THUMBNAIL_CLEANUP_SUBSCRIBER_ID,
        cleanup_activity_thumbnail_for_event,
    )
    registry.register(
        server_settings_events.TILE_SETTINGS_CHANGED,
        THUMBNAIL_SETTINGS_CHANGED_SUBSCRIBER_ID,
        regenerate_thumbnails_for_tile_settings_event,
    )
