"""Public persistence and derivation operations for activity streams."""

from typing import Any

from sqlalchemy.orm import Session

import modules.activities.activity.schema as activity_schema
import modules.activities.activity_streams.contracts as activity_streams_contracts
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.contributors as activities_contributors


def _list_streams_for_activities(
    activity_ids: list[int],
    db: Session,
) -> list[activity_streams_schema.ActivityStreamsRead]:
    """Return streams for activity IDs already scoped by the caller.

    Args:
        activity_ids: IDs of the activities to read.
        db: Database session.

    Returns:
        Streams for activity IDs already scoped by the caller.
    """
    return activity_streams_crud.get_activities_streams(activity_ids, db)


def _store_streams(
    streams: list[activity_streams_contracts.ActivityStreamsCreate],
    activity: activity_schema.ActivityRead,
    db: Session,
) -> None:
    """Store parsed streams for an activity.

    Args:
        streams: Streams to store.
        activity: The parent activity.
        db: Database session.
    """
    activity_streams_crud.create_activity_streams(streams, activity, db)


def _persist_ingestion_component(
    data: Any,
    activity: activity_schema.ActivityRead,
    db: Session,
) -> None:
    """Validate and persist parsed streams through the ingestion contract.

    Args:
        data: The parsed component payload.
        activity: The newly created parent activity.
        db: Database session.
    """
    streams = [
        activity_streams_contracts.ActivityStreamsCreate(
            activity_id=activity.id,
            stream_type=stream.stream_type,
            stream_waypoints=stream.stream_waypoints,
            strava_activity_stream_id=None,
        )
        for stream in data
    ]
    _store_streams(streams, activity, db)


def ingestion_contributor() -> activities_contributors.ActivityIngestionContributor:
    """Return the activity-streams ingestion contribution.

    Returns:
        The contributor.
    """
    return activities_contributors.ActivityIngestionContributor(
        key="streams",
        persist=_persist_ingestion_component,
    )


def _restore_profile_records(
    records: list[dict[str, Any]],
    original_activity_id: int,
    new_activity: activity_schema.ActivityRead,
    db: Session,
) -> int:
    """Validate and restore profile stream records for one activity.

    Args:
        records: Profile records to restore.
        original_activity_id: The activity's ID in the exported archive.
        new_activity: The activity the records are restored onto.
        db: Database session.

    Returns:
        The number of records restored.
    """
    if new_activity.id is None:
        return 0

    streams: list[activity_streams_contracts.ActivityStreamsCreate] = []
    for record in records:
        if record.get("activity_id") != original_activity_id:
            continue
        data = dict(record)
        data.pop("id", None)
        # Archives written while zones were stored carry them; they are computed
        # when the stream is served now, so the stored copy is dropped.
        data.pop("zone_percentages", None)
        data["activity_id"] = new_activity.id
        streams.append(activity_streams_contracts.ActivityStreamsCreate.model_validate(data))

    if streams:
        _store_streams(streams, new_activity, db)
    return len(streams)


def profile_contributor() -> activities_contributors.ProfileActivityContributor:
    """Return the activity-streams profile contribution.

    Returns:
        The contributor.
    """
    return activities_contributors.ProfileActivityContributor(
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
    """Return one unmasked stream for an internal derived artifact.

    No masking is applied: the caller derives an artifact for the owner rather
    than serving a viewer.

    Args:
        activity_id: ID of the activity.
        stream_type: The stream type code.
        db: Database session.

    Returns:
        One unmasked stream for an internal derived artifact.
    """
    return activity_streams_crud.get_activity_stream_by_type(activity_id, stream_type, db)


def get_gps_waypoints_for_activities(activity_ids: list[int], db: Session) -> dict[int, list]:
    """Return GPS waypoints for several activities in one query.

    Activities with no GPS stream are absent from the result.

    Args:
        activity_ids: IDs of the activities to read.
        db: Database session.

    Returns:
        GPS waypoints for several activities in one query.
    """
    return activity_streams_crud.get_gps_stream_waypoints_for_activities(activity_ids, db)
