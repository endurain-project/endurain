"""Activity sets CRUD operations."""

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.logger as core_logger
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.models as activity_models
import modules.activities.activity_sets.models as activity_sets_models
import modules.activities.activity_sets.schema as activity_sets_schema
import modules.server_settings.utils as server_settings_utils


def _to_read_schema(
    orm_set: activity_sets_models.ActivitySets,
    timezone: str | None,
) -> activity_sets_schema.ActivitySetsRead:
    """
    Convert an ORM ActivitySets to a Read schema.

    Args:
        orm_set: The ORM model instance.
        timezone: IANA timezone name from the
            parent activity.

    Returns:
        An ActivitySetsRead schema instance.
    """
    schema = activity_sets_schema.ActivitySetsRead.model_validate(orm_set)
    schema.timezone = timezone
    return schema


@core_decorators.handle_db_errors
def get_activity_sets(
    activity_id: int,
    token_user_id: int,
    db: Session,
) -> list[activity_sets_schema.ActivitySetsRead] | None:
    """
    Retrieve activity sets for a given activity.

    Args:
        activity_id: The activity ID.
        token_user_id: The authenticated user ID.
        db: Database session.

    Returns:
        List of ActivitySetsRead or None if not
            found or hidden.

    Raises:
        HTTPException: If database error occurs.
    """
    activity = activity_crud.get_viewable_activity_by_id_for_user(activity_id, token_user_id, db)

    if not activity:
        return None

    if token_user_id != activity.user_id and activity.hide_workout_sets_steps:
        return None

    stmt = select(activity_sets_models.ActivitySets).where(
        activity_sets_models.ActivitySets.activity_id == activity_id,
    )
    activity_sets = db.scalars(stmt).all()

    if not activity_sets:
        return None

    return [_to_read_schema(s, activity.timezone) for s in activity_sets]


@core_decorators.handle_db_errors
def get_activities_sets(
    activity_ids: list[int],
    token_user_id: int,
    db: Session,
    activities: list[activity_models.Activity] | None = None,
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

    activity_map = {activity.id: activity for activity in activities}

    allowed_ids = [activity.id for activity in activities if activity.user_id == token_user_id]

    if not allowed_ids:
        return []

    sets_stmt = select(activity_sets_models.ActivitySets).where(
        activity_sets_models.ActivitySets.activity_id.in_(allowed_ids)
    )
    activity_sets = db.scalars(sets_stmt).all()

    if not activity_sets:
        return []

    return [
        _to_read_schema(
            s,
            activity_map[s.activity_id].timezone,
        )
        for s in activity_sets
    ]


@core_decorators.handle_db_errors
def get_public_activity_sets(
    activity_id: int,
    db: Session,
) -> list[activity_sets_schema.ActivitySetsRead] | None:
    """
    Retrieve public activity sets for an activity.

    Args:
        activity_id: The activity ID.
        db: Database session.

    Returns:
        List of ActivitySetsRead or None if not
            found, hidden, or not publicly visible.

    Raises:
        HTTPException: If database error occurs.
    """
    activity = activity_crud.get_activity_by_id(activity_id, db)

    if not activity:
        return None

    if activity.hide_workout_sets_steps:
        return None

    server_settings = server_settings_utils.get_server_settings_or_404(db)

    if not server_settings.public_shareable_links:
        return None

    if activity.visibility != 0:
        return None

    stmt = select(activity_sets_models.ActivitySets).where(
        activity_sets_models.ActivitySets.activity_id == activity_id,
    )
    activity_sets = db.scalars(stmt).all()

    if not activity_sets:
        return None

    return [_to_read_schema(s, activity.timezone) for s in activity_sets]


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

    core_logger.print_to_log(
        f"Created {len(sets)} set(s) for activity {activity_id}",
        "debug",
    )


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
