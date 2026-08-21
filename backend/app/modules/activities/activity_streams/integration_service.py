"""Public persistence and derivation operations for activity streams."""

from typing import Any

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.activity_streams.service as activity_streams_service
import modules.activities.activity_streams.subscribers as activity_streams_subscribers
import modules.activities.contributors as activity_contributors


def _list_streams_for_activities(
    activity_ids: list[int],
    db: Session,
) -> list[activity_streams_schema.ActivityStreamsRead]:
    """Return streams for activity IDs already scoped by the caller."""
    return activity_streams_crud.get_activities_streams(activity_ids, db)


def _store_streams(
    streams: list[activity_streams_schema.ActivityStreamsCreate],
    activity: activity_schema.Activity,
    db: Session,
    *,
    commit: bool = True,
) -> None:
    """Store parsed streams for an activity."""
    activity_streams_crud.create_activity_streams(streams, activity, db, commit=commit)


def _persist_ingestion_component(
    data: Any,
    activity: activity_schema.Activity,
    db: Session,
    *,
    commit: bool,
) -> None:
    """Validate and persist parsed streams through the ingestion contract."""
    if activity.id is None:
        raise core_exceptions.ProcessingError("Cannot store streams before the activity has an id")
    streams = [
        activity_streams_schema.ActivityStreamsCreate(
            activity_id=activity.id,
            stream_type=stream.stream_type,
            stream_waypoints=stream.stream_waypoints,
            strava_activity_stream_id=None,
        )
        for stream in data
    ]
    _store_streams(streams, activity, db, commit=commit)


def ingestion_contributor() -> activity_contributors.ActivityIngestionContributor:
    """Return the activity-streams ingestion contribution."""
    return activity_contributors.ActivityIngestionContributor(
        key="streams",
        persist=_persist_ingestion_component,
    )


def _restore_profile_records(
    records: list[dict[str, Any]],
    original_activity_id: int,
    new_activity: activity_schema.Activity,
    db: Session,
) -> int:
    """Validate and restore profile stream records for one activity."""
    if new_activity.id is None:
        return 0

    streams: list[activity_streams_schema.ActivityStreamsCreate] = []
    for record in records:
        if record.get("activity_id") != original_activity_id:
            continue
        data = dict(record)
        data.pop("id", None)
        data["activity_id"] = new_activity.id
        streams.append(activity_streams_schema.ActivityStreamsCreate.model_validate(data))

    if streams:
        _store_streams(streams, new_activity, db)
    return len(streams)


def profile_contributor() -> activity_contributors.ProfileActivityContributor:
    """Return the activity-streams profile contribution."""
    return activity_contributors.ProfileActivityContributor(
        key="streams",
        archive_path="data/activity_streams.json",
        count_key="activity_streams",
        split=True,
        export=_list_streams_for_activities,
        restore=_restore_profile_records,
    )


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
