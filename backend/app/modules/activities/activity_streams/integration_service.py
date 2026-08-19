"""Public persistence and derivation operations for activity streams."""

from sqlalchemy.orm import Session

import modules.activities.activity.schema as activity_schema
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.activity_streams.service as activity_streams_service
import modules.activities.activity_streams.subscribers as activity_streams_subscribers


def list_streams_for_activities(
    activity_ids: list[int],
    db: Session,
) -> list[activity_streams_schema.ActivityStreamsRead]:
    """Return streams for activity IDs already scoped by the caller."""
    return activity_streams_crud.get_activities_streams(activity_ids, db)


def store_streams(
    streams: list[activity_streams_schema.ActivityStreamsCreate],
    activity: activity_schema.Activity,
    db: Session,
    *,
    commit: bool = True,
) -> None:
    """Store parsed streams for an activity."""
    activity_streams_crud.create_activity_streams(streams, activity, db, commit=commit)


def get_stream_for_derivation(
    activity_id: int,
    stream_type: int,
    db: Session,
) -> activity_streams_schema.ActivityStreamsRead | None:
    """Return one unmasked stream for an internal derived artifact."""
    return activity_streams_service.get_stream_for_derivation(activity_id, stream_type, db)


def get_gps_waypoints_for_activities(activity_ids: list[int], db: Session) -> dict[int, list]:
    """Return GPS waypoints for several activities in one query."""
    return activity_streams_service.get_gps_waypoints_for_activities(activity_ids, db)


def recompute_hr_zones_for_user(user_id: int, db: Session) -> None:
    """Recompute stored HR-zone breakdowns after user settings change."""
    activity_streams_service.recompute_hr_zones_for_user(user_id, db)


def run_missing_hr_zone_backfill() -> None:
    """Run the locked scheduled HR-zone reconciliation pass."""
    activity_streams_subscribers.run_missing_hr_zone_backfill()
