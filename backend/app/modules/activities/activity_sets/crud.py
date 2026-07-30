"""Activity sets CRUD operations."""

from collections.abc import Sequence

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.logger as core_logger
import modules.activities.activity.models as activity_models
import modules.activities.activity_sets.models as activity_sets_models
import modules.activities.activity_sets.schema as activity_sets_schema

logger = core_logger.get_logger(__name__)


def _to_read_schema(
    orm_set: activity_sets_models.ActivitySets,
) -> activity_sets_schema.ActivitySetsRead:
    """
    Convert an ORM row to its Read schema.

    Args:
        orm_set: The ORM model instance.

    Returns:
        A ActivitySetsRead schema instance.
    """
    return activity_sets_schema.ActivitySetsRead.model_validate(orm_set)


@core_decorators.handle_db_errors
def get_activity_sets(
    activity_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = 200,
) -> list[activity_sets_schema.ActivitySetsRead]:
    """
    Retrieve one page of an activity's workout sets, in recorded order.

    Performs no access check: whether the caller may read these rows is decided
    by :mod:`modules.activities.activity_sets.service`.

    Args:
        activity_id: The activity ID.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.

    Returns:
        The page of sets, empty when the activity has none.

    Raises:
        ProcessingError: If database error occurs.
    """
    stmt = (
        select(activity_sets_models.ActivitySets)
        .where(activity_sets_models.ActivitySets.activity_id == activity_id)
        .order_by(activity_sets_models.ActivitySets.id)
        .offset((page_number - 1) * num_records)
        .limit(num_records)
    )
    activity_sets = db.scalars(stmt).all()

    return [_to_read_schema(s) for s in activity_sets]


@core_decorators.handle_db_errors
def count_activity_sets(activity_id: int, db: Session) -> int:
    """
    Count an activity's workout sets.

    Args:
        activity_id: The activity ID.
        db: Database session.

    Returns:
        The total number of sets.

    Raises:
        ProcessingError: If database error occurs.
    """
    stmt = select(func.count()).select_from(
        select(activity_sets_models.ActivitySets.id)
        .where(activity_sets_models.ActivitySets.activity_id == activity_id)
        .subquery()
    )
    return db.scalar(stmt) or 0


@core_decorators.handle_db_errors
def get_activities_sets(
    activity_ids: list[int],
    token_user_id: int,
    db: Session,
    activities: Sequence[activity_models.Activity] | None = None,
) -> list[activity_sets_schema.ActivitySetsRead]:
    """
    Retrieve sets for multiple activities.

    Args:
        activity_ids: List of activity IDs.
        token_user_id: The authenticated user ID.
        db: Database session.
        activities: Optional pre-fetched activities.

    Returns:
        List of ActivitySetsRead schemas.

    Raises:
        ProcessingError: If database error occurs.
    """
    if not activity_ids:
        return []

    if not activities:
        stmt = select(activity_models.Activity).where(activity_models.Activity.id.in_(activity_ids))
        activities = db.scalars(stmt).all()

    if not activities:
        return []

    allowed_ids = [activity.id for activity in activities if activity.user_id == token_user_id]

    if not allowed_ids:
        return []

    sets_stmt = select(activity_sets_models.ActivitySets).where(
        activity_sets_models.ActivitySets.activity_id.in_(allowed_ids)
    )
    activity_sets = db.scalars(sets_stmt).all()

    if not activity_sets:
        return []

    return [_to_read_schema(s) for s in activity_sets]


@core_decorators.handle_db_errors
def create_activity_sets(
    activity_sets: list[activity_sets_schema.ActivitySetsCreate | list],
    activity_id: int,
    db: Session,
    *,
    commit: bool = True,
) -> None:
    """
    Bulk create activity sets for an activity.

    Args:
        activity_sets: List of Pydantic schemas or
            raw lists from the FIT parser.
        activity_id: The parent activity ID.
        db: Database session.

    Returns:
        None.

    Raises:
        ProcessingError: If database error occurs.
    """
    sets = []

    for activity_set in activity_sets:
        if isinstance(activity_set, BaseModel):
            db_activity_set = activity_sets_models.ActivitySets(
                activity_id=activity_id,
                duration=activity_set.duration,
                repetitions=(activity_set.repetitions),
                weight=activity_set.weight,
                set_type=activity_set.set_type,
                start_time=(activity_set.start_time),
                category=activity_set.category,
                category_subtype=(activity_set.category_subtype),
            )
        else:
            category = _extract_value(activity_set[5])
            category_subtype = _extract_value(activity_set[6])
            db_activity_set = activity_sets_models.ActivitySets(
                activity_id=activity_id,
                duration=activity_set[0],
                repetitions=activity_set[1],
                weight=activity_set[2],
                set_type=activity_set[3],
                start_time=activity_set[4],
                category=category,
                category_subtype=category_subtype,
            )

        sets.append(db_activity_set)

    db.add_all(sets)
    # commit=False keeps the sets in the caller's open transaction (atomic ingestion).
    if commit:
        db.commit()
    else:
        db.flush()


def _extract_value(
    value: int | tuple | None,
) -> int | None:
    """
    Extract a scalar from a value that may be a tuple.

    Args:
        value: A scalar, tuple, or None.

    Returns:
        The extracted integer value or None.
    """
    if value is None:
        return None
    if isinstance(value, tuple):
        return value[0] if value[0] is not None else None
    return value
