"""Activity sets CRUD operations."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import modules.activities.activity_sets.contracts as activity_sets_contracts
import modules.activities.activity_sets.models as activity_sets_models
import modules.activities.activity_sets.schema as activity_sets_schema
import modules.activities.activity_sets.serializers as activity_sets_serializers


def get_activity_sets(
    activity_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = 200,
) -> list[activity_sets_schema.ActivitySetsRead]:
    """Retrieve one page of an activity's workout sets, in recorded order.

    Performs no access check: whether the caller may read these rows is decided
    by :mod:`modules.activities.activity_sets.service`.

    Args:
        activity_id: The activity ID.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.

    Returns:
        The page of sets, empty when the activity has none.
    """
    stmt = (
        select(activity_sets_models.ActivitySets)
        .where(activity_sets_models.ActivitySets.activity_id == activity_id)
        .order_by(activity_sets_models.ActivitySets.id)
        .offset((page_number - 1) * num_records)
        .limit(num_records)
    )
    activity_sets = db.scalars(stmt).all()

    return [activity_sets_serializers.to_read_schema(s) for s in activity_sets]


def count_activity_sets(activity_id: int, db: Session) -> int:
    """Count an activity's workout sets.

    Args:
        activity_id: The activity ID.
        db: Database session.

    Returns:
        The total number of sets.
    """
    stmt = select(func.count()).select_from(
        select(activity_sets_models.ActivitySets.id)
        .where(activity_sets_models.ActivitySets.activity_id == activity_id)
        .subquery()
    )
    return db.scalar(stmt) or 0


def get_activities_sets(
    activity_ids: list[int],
    db: Session,
) -> list[activity_sets_schema.ActivitySetsRead]:
    """Retrieve the workout sets of several activities at once.

    Performs no access check and joins no parent row: which activities the
    caller may read is decided before this is reached, by the activities
    integration service that owns them.

    Args:
        activity_ids: The activities to read, already scoped to the caller.
        db: Database session.

    Returns:
        The workout sets of those activities, empty when there are none.
    """
    if not activity_ids:
        return []

    stmt = select(activity_sets_models.ActivitySets).where(
        activity_sets_models.ActivitySets.activity_id.in_(activity_ids)
    )
    return [activity_sets_serializers.to_read_schema(row) for row in db.scalars(stmt).all()]


def create_activity_sets(
    activity_sets: list[activity_sets_contracts.ActivitySetsCreate | list],
    activity_id: int,
    db: Session,
) -> None:
    """Stage activity sets for an activity (flushed, not committed).

    Args:
        activity_sets: List of Pydantic schemas or
            raw lists from the FIT parser.
        activity_id: The parent activity ID.
        db: Database session.
    """
    sets = [activity_sets_serializers.to_orm(activity_set, activity_id) for activity_set in activity_sets]

    db.add_all(sets)
    db.flush()
