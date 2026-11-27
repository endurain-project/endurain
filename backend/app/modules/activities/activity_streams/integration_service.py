"""Public persistence and derivation operations for activity streams."""

import uuid
from typing import Any

from pydantic import InstanceOf, TypeAdapter
from sqlalchemy.orm import Session

import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_streams.contracts as activity_streams_contracts
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.contributors as activities_contributors
import modules.users.users_profile.contracts as users_profile_contracts


def _list_streams_for_activities(
    activity_ids: list[uuid.UUID],
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


#: The parsed streams.
_PAYLOAD: TypeAdapter[list[activity_streams_contracts.ParsedStream]] = TypeAdapter(
    list[InstanceOf[activity_streams_contracts.ParsedStream]]
)


#: The parsed samples.
_SAMPLES_PAYLOAD: TypeAdapter[activity_streams_contracts.ParsedSamples] = TypeAdapter(
    InstanceOf[activity_streams_contracts.ParsedSamples]
)


def _persist_ingestion_component(
    data: object,
    activity: activity_schema.ActivityRead,
    db: Session,
) -> None:
    """Validate and persist parsed streams through the ingestion contract.

    Args:
        data: The parsed component payload.
        activity: The newly created parent activity.
        db: Database session.

    Raises:
        ValidationError: When the parser handed something other than parsed streams, before anything is staged.
    """
    streams = [
        activity_streams_contracts.ActivityStreamsCreate(
            activity_id=activity.id,
            stream_type=stream.stream_type,
            # A parsed sample is any mapping (a parser's typed sample, a provider's dict); the row stores a dict.
            stream_waypoints=[dict(waypoint) for waypoint in stream.stream_waypoints],
            strava_activity_stream_id=None,
        )
        for stream in _PAYLOAD.validate_python(data)
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
        clear=activity_streams_crud.delete_activity_streams,
    )


def _persist_samples(
    data: object,
    activity: activity_schema.ActivityRead,
    db: Session,
) -> None:
    """Validate and persist parsed samples through the ingestion contract.

    Args:
        data: The parsed component payload.
        activity: The newly created parent activity.
        db: Database session.

    Raises:
        ValidationError: When the parser handed something other than parsed samples, before anything is staged.
    """
    activity_streams_crud.create_activity_samples(activity.id, _SAMPLES_PAYLOAD.validate_python(data), db)


def samples_ingestion_contributor() -> activities_contributors.ActivityIngestionContributor:
    """Return the activity-samples ingestion contribution.

    Returns:
        The contributor.
    """
    return activities_contributors.ActivityIngestionContributor(
        key="samples",
        persist=_persist_samples,
        clear=activity_streams_crud.delete_activity_samples,
    )


def _restore_profile_records(
    records: list[dict[str, Any]],
    original_activity_id: uuid.UUID,
    new_activity: activity_schema.ActivityRead,
    db: Session,
) -> int:
    """Validate and restore profile stream records for one activity.

    Args:
        records: Profile records to restore.
        original_activity_id: The activity id the records were exported under.
        new_activity: The activity the records are restored onto.
        db: Database session.

    Returns:
        The number of records restored.
    """
    if new_activity.id is None:
        return 0

    streams: list[activity_streams_contracts.ActivityStreamsCreate] = []
    for record in records:
        if users_profile_contracts.archived_id(record.get("activity_id")) != original_activity_id:
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


def get_route_waypoints_for_activities(
    activity_ids: list[uuid.UUID], db: Session
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """Return the route of several activities in one query: each one's own GPS waypoints.

    A multisport activity has no stream of its own, so its route is its legs' GPS waypoints joined in the legs' start
    order; a leg without a map adds nothing. An activity with no route is absent from the result.

    Args:
        activity_ids: IDs of the activities to read.
        db: Database session.

    Returns:
        The route waypoints by activity ID.
    """
    legs = activity_integration.get_leg_ids_by_parent(activity_ids, db)
    waypoints = activity_streams_crud.get_gps_stream_waypoints_for_activities(
        [*activity_ids, *(leg_id for leg_ids in legs.values() for leg_id in leg_ids)], db
    )
    routes: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for activity_id in activity_ids:
        route = (
            [point for leg_id in legs[activity_id] for point in waypoints.get(leg_id, [])]
            if activity_id in legs
            else waypoints.get(activity_id)
        )
        if route:
            routes[activity_id] = route
    return routes
