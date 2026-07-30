"""Activity sets CRUD operations."""

from collections.abc import Sequence

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.logger as core_logger
import modules.activities.activity.crud as activity_crud
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
    token_user_id: int,
    db: Session,
) -> list[activity_sets_schema.ActivitySetsRead]:
    """
    Retrieve activity sets for a given activity.

    Args:
        activity_id: The activity ID.
        token_user_id: The authenticated user ID.
        db: Database session.

    Returns:
        The activity's sets, empty when the activity is not visible to the
        caller, its sets are hidden, or it has none.

    Raises:
        HTTPException: If database error occurs.
    """
    activity = activity_crud.get_viewable_activity_by_id_for_user(activity_id, token_user_id, db)

    if not activity:
        return []

    if token_user_id != activity.user_id and activity.hide_workout_sets_steps:
        return []

    stmt = select(activity_sets_models.ActivitySets).where(
        activity_sets_models.ActivitySets.activity_id == activity_id,
    )
    activity_sets = db.scalars(stmt).all()

    if not activity_sets:
        return []

    return [_to_read_schema(s) for s in activity_sets]


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
        HTTPException: If database error occurs.
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
def get_public_activity_sets(
    activity_id: int,
    db: Session,
) -> list[activity_sets_schema.ActivitySetsRead]:
    """
    Retrieve public activity sets for an activity.

    Args:
        activity_id: The activity ID.
        db: Database session.

    Returns:
        The activity's sets, empty when it is not found, hidden, or not
        publicly visible — indistinguishable on purpose, since this endpoint is
        unauthenticated.

    Raises:
        HTTPException: If database error occurs.
    """
    activity = activity_crud.get_public_activity_for_child_read(activity_id, db, hide_attr="hide_workout_sets_steps")

    if not activity:
        return []

    stmt = select(activity_sets_models.ActivitySets).where(
        activity_sets_models.ActivitySets.activity_id == activity_id,
    )
    activity_sets = db.scalars(stmt).all()

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
        HTTPException: If database error occurs.
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

    logger.debug("Created activity sets", extra=core_logger.context(activity_id=activity_id, count=len(sets)))


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
