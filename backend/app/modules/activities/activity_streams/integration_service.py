"""Public persistence and derivation operations for activity streams."""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import asdict
from typing import Any

from pydantic import InstanceOf, TypeAdapter
from sqlalchemy.orm import Session

import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_streams.contracts as activity_streams_contracts
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_streams.samples as activity_streams_samples
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.contributors as activities_contributors
import modules.users.users_profile.contracts as users_profile_contracts

#: The parsed samples.
_SAMPLES_PAYLOAD: TypeAdapter[activity_streams_contracts.ParsedSamples] = TypeAdapter(
    InstanceOf[activity_streams_contracts.ParsedSamples]
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


def _clear_samples(activity_id: uuid.UUID, db: Session) -> None:
    """Stage the removal of an activity's samples and of the old waypoint streams it may still have.

    A reprocess stores the samples again, so a stream stored before v0.22 must not outlive it.

    Args:
        activity_id: ID of the activity.
        db: Database session.
    """
    activity_streams_crud.delete_activity_samples(activity_id, db)
    activity_streams_crud.delete_activity_streams(activity_id, db)


def samples_ingestion_contributor() -> activities_contributors.ActivityIngestionContributor:
    """Return the activity-samples ingestion contribution.

    Returns:
        The contributor.
    """
    return activities_contributors.ActivityIngestionContributor(
        key="samples",
        persist=_persist_samples,
        clear=_clear_samples,
    )


def _legacy_samples_of(
    activity_ids: list[uuid.UUID], db: Session
) -> dict[uuid.UUID, activity_streams_contracts.ParsedSamples]:
    """Convert the old waypoint streams of activities to samples, without persisting them.

    Args:
        activity_ids: IDs of the activities to read, already scoped to the caller.
        db: Database session.

    Returns:
        The samples by activity ID; an activity with no old stream holding a value is absent.
    """
    converted: dict[uuid.UUID, activity_streams_contracts.ParsedSamples] = {}
    for activity_id in activity_ids:
        streams = activity_streams_crud.get_activity_streams(activity_id, db)
        activity = activity_integration.get_activity(activity_id, db) if streams else None
        if activity is None or activity.start_time is None:
            continue
        samples = activity_streams_samples.samples_from_streams(streams, activity.start_time)
        if samples is not None:
            converted[activity_id] = samples
    return converted


def convert_legacy_streams(activity_id: uuid.UUID, db: Session) -> bool:
    """Stage the conversion of an activity's old waypoint streams to its samples row, and delete the old streams.

    For an activity no reprocess rewrote, whose streams are all it has: no file, an unreadable one, or none that
    holds its session. The activity is locked first, so a recompute that stores samples at the same time is waited
    for, and an activity that already has samples only loses its old streams. Streams that hold no sample are deleted
    too, as a read of them yields nothing. The activity takes the first positioned sample as its start point when it
    has none, which is what the thumbnail and location backfills look for. The caller commits.

    Args:
        activity_id: ID of the activity.
        db: Database session.

    Returns:
        ``True`` when the activity had old streams and they were deleted.
    """
    if not activity_integration.lock_activity(activity_id, db):
        return False
    streams = activity_streams_crud.get_activity_streams(activity_id, db)
    if not streams:
        return False
    activity = activity_integration.get_activity(activity_id, db)
    if activity is not None and activity.start_time is not None:
        samples = activity_streams_crud.get_activity_samples(activity_id, db)
        if samples is None:
            samples = activity_streams_samples.samples_from_streams(streams, activity.start_time)
            if samples is not None:
                activity_streams_crud.create_activity_samples(activity_id, samples, db)
        start = None if samples is None else _route_of(samples.latitude, samples.longitude)[:1]
        if start:
            activity_integration.set_start_point(activity_id, start[0][0], start[0][1], db)
    activity_streams_crud.delete_activity_streams(activity_id, db)
    return True


def _samples_for_activities(
    activity_ids: list[uuid.UUID], db: Session
) -> dict[uuid.UUID, activity_streams_contracts.ParsedSamples]:
    """Return the samples of several activities, converting the old streams of those with no samples row.

    Activities stored before v0.22 have only old streams until the reprocess converts them.

    Args:
        activity_ids: IDs of the activities to read, already scoped to the caller.
        db: Database session.

    Returns:
        The samples by activity ID; an activity with none is absent.
    """
    stored = activity_streams_crud.get_activities_samples(activity_ids, db)
    return stored | _legacy_samples_of([activity_id for activity_id in activity_ids if activity_id not in stored], db)


def _list_samples_for_activities(
    activity_ids: list[uuid.UUID],
    db: Session,
) -> list[activity_streams_schema.ActivitySamplesArchive]:
    """Return the samples of activity IDs already scoped by the caller, as archive records.

    Args:
        activity_ids: IDs of the activities to read.
        db: Database session.

    Returns:
        One record per activity that has samples.
    """
    return [
        activity_streams_schema.ActivitySamplesArchive(activity_id=activity_id, **asdict(samples))
        for activity_id, samples in _samples_for_activities(activity_ids, db).items()
    ]


def _restore_samples_records(
    records: list[dict[str, Any]],
    original_activity_id: uuid.UUID,
    new_activity: activity_schema.ActivityRead,
    db: Session,
) -> int:
    """Validate and restore the archived samples of one activity.

    Args:
        records: Profile records to restore.
        original_activity_id: The activity id the records were exported under.
        new_activity: The activity the records are restored onto.
        db: Database session.

    Returns:
        The number of records restored.

    Raises:
        ValidationError: When a record is not valid samples.
    """
    for record in records:
        if users_profile_contracts.archived_id(record.get("activity_id")) != original_activity_id:
            continue
        data = dict(record)
        data["activity_id"] = new_activity.id
        samples = activity_streams_schema.ActivitySamplesArchive.model_validate(data).to_samples()
        activity_streams_crud.create_activity_samples(new_activity.id, samples, db)
        return 1
    return 0


def _restore_legacy_stream_records(
    records: list[dict[str, Any]],
    original_activity_id: uuid.UUID,
    new_activity: activity_schema.ActivityRead,
    db: Session,
) -> int:
    """Validate the old waypoint stream records of one activity and restore them as samples.

    An archive written before v0.22 carries the streams of an activity as one record per type.

    Args:
        records: Profile records to restore.
        original_activity_id: The activity id the records were exported under.
        new_activity: The activity the records are restored onto.
        db: Database session.

    Returns:
        The number of stream records read.

    Raises:
        ValidationError: When a record is not a valid stream.
    """
    streams: list[activity_streams_schema.ActivityStreamsBase] = []
    for record in records:
        if users_profile_contracts.archived_id(record.get("activity_id")) != original_activity_id:
            continue
        data = dict(record)
        data.pop("id", None)
        # Archives written while zones were stored carry them; they are computed when the streams are served.
        data.pop("zone_percentages", None)
        data["activity_id"] = new_activity.id
        streams.append(activity_streams_schema.ActivityStreamsBase.model_validate(data))

    if new_activity.start_time is not None:
        samples = activity_streams_samples.samples_from_streams(streams, new_activity.start_time)
        if samples is not None:
            activity_streams_crud.create_activity_samples(new_activity.id, samples, db)
    return len(streams)


def profile_contributor() -> activities_contributors.ProfileActivityContributor:
    """Return the activity-samples profile contribution.

    Returns:
        The contributor.
    """
    return activities_contributors.ProfileActivityContributor(
        key="samples",
        archive_path="data/activity_samples.json",
        count_key="activity_samples",
        split=True,
        export=_list_samples_for_activities,
        restore=_restore_samples_records,
    )


def legacy_profile_contributor() -> activities_contributors.ProfileActivityContributor:
    """Return the contribution that reads the streams of an archive written before v0.22.

    It only restores: the export writes samples.

    Returns:
        The contributor.
    """
    return activities_contributors.ProfileActivityContributor(
        key="streams",
        archive_path="data/activity_streams.json",
        count_key="activity_streams",
        split=True,
        export=None,
        restore=_restore_legacy_stream_records,
    )


def _route_of(
    latitudes: Sequence[float | None] | None, longitudes: Sequence[float | None] | None
) -> list[tuple[float, float]]:
    """Return the ``(latitude, longitude)`` of the samples that have a position, in order.

    Args:
        latitudes: Latitude per sample, or ``None`` when there is none.
        longitudes: Longitude per sample, or ``None`` when there is none.

    Returns:
        The route points.
    """
    if latitudes is None or longitudes is None:
        return []
    return [(lat, lon) for lat, lon in zip(latitudes, longitudes, strict=True) if lat is not None and lon is not None]


def _routes(
    activity_ids: list[uuid.UUID],
    own_routes: Callable[[list[uuid.UUID]], dict[uuid.UUID, list[tuple[float, float]]]],
    db: Session,
) -> dict[uuid.UUID, list[tuple[float, float]]]:
    """Return the route of several activities, a multisport activity's being its legs' joined in start order.

    A multisport activity has no samples of its own; a leg without a position adds nothing.

    Args:
        activity_ids: IDs of the activities to read.
        own_routes: Reads the route of each activity and leg from its own samples.
        db: Database session.

    Returns:
        The route points by activity ID; an activity with no route is absent.
    """
    legs = activity_integration.get_leg_ids_by_parent(activity_ids, db)
    own = own_routes([*activity_ids, *(leg_id for leg_ids in legs.values() for leg_id in leg_ids)])
    routes: dict[uuid.UUID, list[tuple[float, float]]] = {}
    for activity_id in activity_ids:
        route = (
            [point for leg_id in legs[activity_id] for point in own.get(leg_id, [])]
            if activity_id in legs
            else own.get(activity_id, [])
        )
        if route:
            routes[activity_id] = route
    return routes


def get_routes_for_activities(activity_ids: list[uuid.UUID], db: Session) -> dict[uuid.UUID, list[tuple[float, float]]]:
    """Return the route of several activities from their samples' positions, with one query that reads only those.

    A route is the ``(latitude, longitude)`` of the samples that have a position, in order. A multisport activity
    has no samples of its own, so its route is its legs' routes joined in the legs' start order; a leg without a
    position adds nothing. An activity with no route is absent from the result.

    Args:
        activity_ids: IDs of the activities to read.
        db: Database session.

    Returns:
        The route points by activity ID.
    """

    def own_routes(ids: list[uuid.UUID]) -> dict[uuid.UUID, list[tuple[float, float]]]:
        return {
            activity_id: _route_of(latitudes, longitudes)
            for activity_id, (latitudes, longitudes) in activity_streams_crud.get_activities_positions(ids, db).items()
        }

    return _routes(activity_ids, own_routes, db)


def get_routes_for_reprocess(activity_ids: list[uuid.UUID], db: Session) -> dict[uuid.UUID, list[tuple[float, float]]]:
    """Return the routes of several activities, from their old streams when they have no samples yet.

    The routes are those of :func:`get_routes_for_activities`. The reprocess compares an activity's route before and
    after, and an activity stored before v0.22 has only old streams until the reprocess converts it.

    Args:
        activity_ids: IDs of the activities to read.
        db: Database session.

    Returns:
        The route points by activity ID.
    """

    def own_routes(ids: list[uuid.UUID]) -> dict[uuid.UUID, list[tuple[float, float]]]:
        return {
            activity_id: _route_of(samples.latitude, samples.longitude)
            for activity_id, samples in _samples_for_activities(ids, db).items()
        }

    return _routes(activity_ids, own_routes, db)
