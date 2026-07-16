"""Event subscribers wiring the thumbnail subsystem to activity lifecycle events.

Registered once at startup (before the event bus starts). In the ``local``
profile the in-process bus runs these inline, synchronously, before the
producing request returns — behaviourally identical to inline generation; in a
``distributed`` profile a Redis-Streams consumer runs them later, at-least-once,
against object storage (foundations plan §13).

Two shapes of handler live here. The ``*_for_event`` cores **raise** on failure
so the durable-job runner can retry and eventually dead-letter them (used when
durable jobs are enabled). The ``on_*`` bus subscribers wrap those cores and
**swallow** errors so a thumbnail failure never breaks activity import or
deletion (used on the best-effort bus path). Either way the scheduled backfill
(:func:`service.generate_missing_activity_thumbnails`) is the safety net for the
create path.
"""

import activities.activity.events as activity_events
import activities.activity_streams.constants as activity_streams_constants
import activities.activity_streams.crud as activity_streams_crud
import activities.activity_thumbnail.service as activity_thumbnail_service
import core.database as core_database
import core.logger as core_logger
import infra.runtime as platform_runtime
from infra.events import Event
from infra.jobs.registry import JobHandlerRegistry
from infra.providers import EventBusProvider

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
    activity_id = event.payload.get("activity_id")
    user_id = event.payload.get("user_id")
    if not isinstance(activity_id, int) or not isinstance(user_id, int):
        return
    storage = platform_runtime.get_active_platform().storage
    with core_database.SessionLocal() as db:
        waypoints = activity_streams_crud.get_activity_stream_by_type(
            activity_id, activity_streams_constants.STREAM_TYPE_MAP, user_id, db
        )
        if waypoints is None or len(waypoints.stream_waypoints) < _MIN_WAYPOINTS:
            return
        tile_url, background_color, api_key = activity_thumbnail_service.resolve_tile_settings(db)
        activity_thumbnail_service.generate_and_store_thumbnail(
            activity_id,
            waypoints.stream_waypoints,
            storage,
            db,
            tile_url=tile_url,
            background_color=background_color,
            api_key=api_key,
        )


def on_activity_created_generate_thumbnail(event: Event) -> None:
    """Bus subscriber: generate a map thumbnail, swallowing any error.

    Wraps :func:`generate_activity_thumbnail_for_event` so a thumbnail failure
    never breaks activity import (the hourly backfill regenerates any missed).

    Args:
        event: The ``activity.created`` event.

    Returns:
        None.
    """
    try:
        generate_activity_thumbnail_for_event(event)
    except Exception as err:
        core_logger.print_to_log(
            f"activity.created thumbnail handler failed for activity {event.payload.get('activity_id')}: {err}",
            "error",
            exc=err,
        )


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
    activity_id = event.payload.get("activity_id")
    if not isinstance(activity_id, int):
        return
    storage = platform_runtime.get_active_platform().storage
    activity_thumbnail_service.delete_activity_thumbnail(activity_id, storage)


def on_activity_deleted_cleanup_thumbnail(event: Event) -> None:
    """Bus subscriber: delete a deleted activity's thumbnail, swallowing any error.

    Wraps :func:`cleanup_activity_thumbnail_for_event` so a cleanup failure never
    breaks activity deletion.

    Args:
        event: The ``activity.deleted`` event.

    Returns:
        None.
    """
    try:
        cleanup_activity_thumbnail_for_event(event)
    except Exception as err:
        core_logger.print_to_log(
            f"activity.deleted thumbnail cleanup failed for activity {event.payload.get('activity_id')}: {err}",
            "error",
            exc=err,
        )


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
