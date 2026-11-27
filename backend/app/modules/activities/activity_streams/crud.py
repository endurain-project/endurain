"""CRUD operations for activity stream data."""

import uuid
from dataclasses import asdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.contracts as activity_streams_contracts
import modules.activities.activity_streams.models as activity_streams_models
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.activity_streams.serializers as activity_streams_serializers


def get_activity_streams(
    activity_id: uuid.UUID,
    db: Session,
) -> list[activity_streams_schema.ActivityStreamsRead]:
    """Get every stream belonging to an activity.

    Performs no access check and no per-type masking: both are decided by
    :mod:`modules.activities.activity_streams.service`.

    Args:
        activity_id: The activity identifier.
        db: Database session.

    Returns:
        The activity's streams, empty when it has none.
    """
    stmt = select(activity_streams_models.ActivityStreams).where(
        activity_streams_models.ActivityStreams.activity_id == activity_id,
    )
    activity_streams: list[activity_streams_models.ActivityStreams] = list(db.scalars(stmt).all())

    return activity_streams_serializers.to_read_schemas(activity_streams)


def delete_activity_streams(activity_id: uuid.UUID, db: Session) -> None:
    """Stage the removal of every stream an activity stored before the columnar samples (flushed, not committed).

    Args:
        activity_id: The parent activity ID.
        db: Database session.
    """
    db.execute(
        delete(activity_streams_models.ActivityStreams).where(
            activity_streams_models.ActivityStreams.activity_id == activity_id
        )
    )
    db.flush()


def create_activity_samples(
    activity_id: uuid.UUID,
    samples: activity_streams_contracts.ParsedSamples,
    db: Session,
) -> activity_streams_models.ActivitySamples:
    """Stage the columnar samples of an activity and flush; the caller commits.

    Args:
        activity_id: The activity the samples belong to.
        samples: The validated samples.
        db: Database session.

    Returns:
        The staged row.
    """
    values = asdict(samples)
    # The driver refuses an array that mixes ints and floats, and a whole-number sample is an int.
    for name in activity_streams_constants.SAMPLE_CHANNELS:
        if values[name] is not None:
            values[name] = [None if value is None else float(value) for value in values[name]]
    row = activity_streams_models.ActivitySamples(activity_id=activity_id, **values)
    db.add(row)
    db.flush()
    return row


def get_activity_samples(
    activity_id: uuid.UUID,
    db: Session,
) -> activity_streams_contracts.ParsedSamples | None:
    """Get the columnar samples of an activity.

    Performs no access check and no masking: both are decided by the service that reads them.

    Args:
        activity_id: The activity identifier.
        db: Database session.

    Returns:
        The samples, or ``None`` when the activity has none.
    """
    row = db.get(activity_streams_models.ActivitySamples, activity_id)
    return None if row is None else activity_streams_serializers.to_parsed_samples(row)


def get_activities_samples(
    activity_ids: list[uuid.UUID],
    db: Session,
) -> dict[uuid.UUID, activity_streams_contracts.ParsedSamples]:
    """Get the columnar samples of several activities in one query.

    Performs no access check: which activities the caller may read is decided before this is reached.

    Args:
        activity_ids: The activities to read, already scoped to the caller.
        db: Database session.

    Returns:
        The samples keyed by activity identifier; an activity without samples is absent.
    """
    if not activity_ids:
        return {}
    stmt = select(activity_streams_models.ActivitySamples).where(
        activity_streams_models.ActivitySamples.activity_id.in_(activity_ids)
    )
    return {row.activity_id: activity_streams_serializers.to_parsed_samples(row) for row in db.scalars(stmt).all()}


def delete_activity_samples(activity_id: uuid.UUID, db: Session) -> None:
    """Delete the columnar samples of an activity; the caller commits.

    Args:
        activity_id: The activity identifier.
        db: Database session.
    """
    db.execute(
        delete(activity_streams_models.ActivitySamples).where(
            activity_streams_models.ActivitySamples.activity_id == activity_id
        )
    )
    db.flush()


def get_activities_positions(
    activity_ids: list[uuid.UUID],
    db: Session,
) -> dict[uuid.UUID, tuple[list[float | None], list[float | None]]]:
    """Get the latitude and longitude columns of several activities' samples in one query, and nothing else.

    Performs no access check: which activities the caller may read is decided before this is reached.

    Args:
        activity_ids: The activities to read, already scoped to the caller.
        db: Database session.

    Returns:
        ``(latitudes, longitudes)`` by activity identifier; an activity without positioned samples is absent.
    """
    if not activity_ids:
        return {}
    model = activity_streams_models.ActivitySamples
    stmt = select(model.activity_id, model.latitude, model.longitude).where(
        model.activity_id.in_(activity_ids), model.latitude.is_not(None)
    )
    return {row.activity_id: (row.latitude, row.longitude) for row in db.execute(stmt)}
