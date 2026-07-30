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

import core.database as core_database
import core.logger as core_logger
import infra.event_versioning as platform_event_versioning
import infra.runtime as platform_runtime
import modules.activities.activity.events as activity_events
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_thumbnail.service as activity_thumbnail_service
from infra.events import Event
from infra.jobs.registry import JobHandlerRegistry
from infra.providers import EventBusProvider
from infra.subscribers import best_effort

logger = core_logger.get_logger(__name__)

# The minimum GPS waypoints needed to draw a route; below this there is no map
# to render (non-GPS activities such as strength training cost nothing).
_MIN_WAYPOINTS = 2

# Stable durable-subscriber ids (independent of module path) so job history and
# dedup survive refactors.
THUMBNAIL_GENERATE_SUBSCRIBER_ID = "activity_thumbnail.generate"
THUMBNAIL_CLEANUP_SUBSCRIBER_ID = "activity_thumbnail.cleanup"


def generate_activity_thumbnail_for_event(event: Event) -> None:
    """Generate a map thumbnail for a newly created activity; raises on failure.

    The durable-job handler for ``activity.created``: any error propagates so the
    runner retries and eventually dead-letters the job. No-ops for activities
    without at least two GPS waypoints (non-GPS activities cost nothing).

    Args:
        event: The ``activity.created`` event (payload
            ``{"activity_id": int, "user_id": int}``).

    Returns:
        None.
    """
    payload = platform_event_versioning.parse_payload(activity_events.ActivityCreatedPayload, event)
    storage = platform_runtime.get_active_platform().storage
    with core_database.SessionLocal() as db:
        waypoints = activity_streams_crud.get_activity_stream_by_type(
            payload.activity_id, activity_streams_constants.STREAM_TYPE_MAP, db
        )
        if waypoints is None or len(waypoints.stream_waypoints) < _MIN_WAYPOINTS:
            # Logged because "my activity has no thumbnail" is otherwise
            # indistinguishable from a failure.
            logger.debug(
                "Skipping thumbnail generation: too few GPS waypoints",
                extra=core_logger.context(
                    activity_id=payload.activity_id,
                    user_id=payload.user_id,
                    waypoint_count=0 if waypoints is None else len(waypoints.stream_waypoints),
                    minimum_waypoints=_MIN_WAYPOINTS,
                ),
            )
            return
        tile_url, background_color, api_key = activity_thumbnail_service.resolve_tile_settings(db)
        activity_thumbnail_service.generate_and_store_thumbnail(
            payload.activity_id,
            waypoints.stream_waypoints,
            storage,
            db,
            tile_url=tile_url,
            background_color=background_color,
            api_key=api_key,
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

    Returns:
        None.
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


def register_thumbnail_subscribers(events: EventBusProvider) -> None:
    """Register the thumbnail subscribers for the activity lifecycle events.

    Called once at startup before the event bus is started.

    Args:
        events: The event-bus provider to subscribe on.

    Returns:
        None.
    """
    events.subscribe(activity_events.ACTIVITY_CREATED, on_activity_created_generate_thumbnail)
    events.subscribe(activity_events.ACTIVITY_DELETED, on_activity_deleted_cleanup_thumbnail)


def register_thumbnail_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the thumbnail handlers as durable job subscribers.

    Used when durable jobs are enabled: the outbox relay fans ``activity.created``
    / ``activity.deleted`` out into jobs keyed by these subscriber ids, and the
    worker resolves them back to the raising ``*_for_event`` cores (so failures
    are retried and eventually dead-lettered).

    Args:
        registry: The durable-subscriber registry to register on.

    Returns:
        None.
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
