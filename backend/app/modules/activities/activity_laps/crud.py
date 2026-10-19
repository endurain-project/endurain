"""Activity laps CRUD operations."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import modules.activities.activity_laps.models as activity_laps_models
import modules.activities.activity_laps.schema as activity_laps_schema
import modules.activities.activity_laps.serializers as activity_laps_serializers


def get_activity_laps(
    activity_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = 200,
) -> list[activity_laps_schema.ActivityLapsRead]:
    """Retrieve one page of an activity's laps, in recorded order.

    Performs no access check: whether the caller may read these rows is decided
    by :mod:`modules.activities.activity_laps.service`.

    Args:
        activity_id: The activity ID.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.

    Returns:
        The page of laps, empty when the activity has none.
    """
    stmt = (
        select(activity_laps_models.ActivityLaps)
        .where(activity_laps_models.ActivityLaps.activity_id == activity_id)
        # Ordered so paging is stable; the id is the insertion order the parser
        # produced, which is the order the laps were recorded in.
        .order_by(activity_laps_models.ActivityLaps.id)
        .offset((page_number - 1) * num_records)
        .limit(num_records)
    )
    activity_laps = db.scalars(stmt).all()

    return [activity_laps_serializers.to_read_schema(lap) for lap in activity_laps]


def count_activity_laps(activity_id: int, db: Session) -> int:
    """Count an activity's laps.

    Args:
        activity_id: The activity ID.
        db: Database session.

    Returns:
        The total number of laps.
    """
    stmt = select(func.count()).select_from(
        select(activity_laps_models.ActivityLaps.id)
        .where(activity_laps_models.ActivityLaps.activity_id == activity_id)
        .subquery()
    )
    return db.scalar(stmt) or 0


def get_activities_laps(
    activity_ids: list[int],
    db: Session,
) -> list[activity_laps_schema.ActivityLapsRead]:
    """Retrieve the laps of several activities at once.

    Performs no access check and joins no parent row: which activities the
    caller may read is decided before this is reached, by the activities
    integration service that owns them.

    Args:
        activity_ids: The activities to read, already scoped to the caller.
        db: Database session.

    Returns:
        The laps of those activities, empty when there are none.
    """
    if not activity_ids:
        return []

    stmt = select(activity_laps_models.ActivityLaps).where(
        activity_laps_models.ActivityLaps.activity_id.in_(activity_ids)
    )
    return [activity_laps_serializers.to_read_schema(row) for row in db.scalars(stmt).all()]


def create_activity_laps(
    activity_laps: list[dict],
    activity_id: int,
    db: Session,
) -> None:
    """Stage activity laps for an activity (flushed, not committed).

    Args:
        activity_laps: List of lap dicts from
            file parsers.
        activity_id: The parent activity ID.
        db: Database session.
    """
    laps = [activity_laps_serializers.to_orm(lap, activity_id) for lap in activity_laps]

    db.add_all(laps)
    db.flush()
