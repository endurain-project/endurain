"""Event subscribers wiring the thumbnail subsystem to activity lifecycle events.

Registered once at startup (before the event bus starts). In the ``local``
profile the in-process bus runs these inline, synchronously, before the
producing request returns — behaviourally identical to inline generation; in a
``distributed`` profile a Redis-Streams consumer runs them later, at-least-once,
against object storage (foundations plan §13).

Both handlers swallow their errors: a thumbnail failure must never break activity
import or deletion. The scheduled backfill (:func:`service.generate_missing_activity_thumbnails`)
is the safety net for anything missed on the create path.
"""

import activities.activity.events as activity_events
import activities.activity_streams.constants as activity_streams_constants
import activities.activity_streams.crud as activity_streams_crud
import activities.activity_thumbnail.service as activity_thumbnail_service
import core.database as core_database
import core.logger as core_logger
import core.platform.runtime as platform_runtime
from core.platform.events import Event
from core.platform.providers import EventBusProvider

# The minimum GPS waypoints needed to draw a route; below this there is no map
# to render (non-GPS activities such as strength training cost nothing).
_MIN_WAYPOINTS = 2


def on_activity_created_generate_thumbnail(event: Event) -> None:
    """Subscriber: generate a map thumbnail for a newly created activity.

    No-ops for activities without at least two GPS waypoints. Errors are logged
    and swallowed — a thumbnail failure must never break activity import (the
    hourly backfill regenerates any that were missed).

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
    try:
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
    except Exception as err:
        core_logger.print_to_log(
            f"activity.created thumbnail handler failed for activity {activity_id}: {err}",
            "error",
            exc=err,
        )


def on_activity_deleted_cleanup_thumbnail(event: Event) -> None:
    """Subscriber: delete a deleted activity's stored thumbnail.

    Mirrors the create path — the subsystem that produced the artifact removes
    it. The storage key is derived from the activity ID, so the already-deleted
    row is not needed, and the delete is idempotent (safe when no thumbnail ever
    existed). Errors are logged and swallowed.

    Args:
        event: The ``activity.deleted`` event (payload ``{"activity_id": int}``).

    Returns:
        None.
    """
    activity_id = event.payload.get("activity_id")
    if not isinstance(activity_id, int):
        return
    try:
        storage = platform_runtime.get_active_platform().storage
        activity_thumbnail_service.delete_activity_thumbnail(activity_id, storage)
    except Exception as err:
        core_logger.print_to_log(
            f"activity.deleted thumbnail cleanup failed for activity {activity_id}: {err}",
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
