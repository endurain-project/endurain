"""Activity laps CRUD operations."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.logger as core_logger
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.models as activity_models
import modules.activities.activity_laps.models as activity_laps_models
import modules.activities.activity_laps.schema as activity_laps_schema

_LAP_COLUMNS: tuple[str, ...] = (
    "start_time",
    "start_position_lat",
    "start_position_long",
    "end_position_lat",
    "end_position_long",
    "total_elapsed_time",
    "total_timer_time",
    "total_distance",
    "total_cycles",
    "total_calories",
    "avg_heart_rate",
    "max_heart_rate",
    "avg_cadence",
    "max_cadence",
    "avg_power",
    "max_power",
    "total_ascent",
    "total_descent",
    "intensity",
    "lap_trigger",
    "sport",
    "sub_sport",
    "normalized_power",
    "total_work",
    "avg_vertical_oscillation",
    "avg_stance_time",
    "avg_fractional_cadence",
    "max_fractional_cadence",
    "enhanced_avg_pace",
    "enhanced_avg_speed",
    "enhanced_max_pace",
    "enhanced_max_speed",
    "enhanced_min_altitude",
    "enhanced_max_altitude",
    "avg_vertical_ratio",
    "avg_step_length",
)


def _to_read_schema(
    orm_lap: activity_laps_models.ActivityLaps,
) -> activity_laps_schema.ActivityLapsRead:
    """
    Convert an ORM row to its Read schema.

    Args:
        orm_lap: The ORM model instance.

    Returns:
        A ActivityLapsRead schema instance.
    """
    return activity_laps_schema.ActivityLapsRead.model_validate(orm_lap)


@core_decorators.handle_db_errors
def get_activity_laps(
    activity_id: int,
    token_user_id: int,
    db: Session,
) -> list[activity_laps_schema.ActivityLapsRead] | None:
    """
    Retrieve activity laps for a given activity.

    Args:
        activity_id: The activity ID.
        token_user_id: The authenticated user ID.
        db: Database session.

    Returns:
        List of ActivityLapsRead or None if not
            found or hidden.

    Raises:
        HTTPException: If database error occurs.
    """
    activity = activity_crud.get_viewable_activity_by_id_for_user(activity_id, token_user_id, db)

    if not activity:
        return None

    if token_user_id != activity.user_id and activity.hide_laps:
        return None

    stmt = select(activity_laps_models.ActivityLaps).where(
        activity_laps_models.ActivityLaps.activity_id == activity_id,
    )
    activity_laps = db.scalars(stmt).all()

    if not activity_laps:
        return None

    return [_to_read_schema(lap) for lap in activity_laps]


@core_decorators.handle_db_errors
def get_activities_laps(
    activity_ids: list[int],
    token_user_id: int,
    db: Session,
    prefetched_activities: list[activity_models.Activity] | None = None,
) -> list[activity_laps_schema.ActivityLapsRead]:
    """
    Retrieve laps for multiple activities.

    Args:
        activity_ids: List of activity IDs.
        token_user_id: The authenticated user ID.
        db: Database session.
        prefetched_activities: Optional pre-fetched
            activities (avoids a re-query when the
            caller already has them in scope).

    Returns:
        List of ActivityLapsRead schemas.

    Raises:
        HTTPException: If database error occurs.
    """
    if not activity_ids:
        return []

    activities_list: Sequence[activity_models.Activity] | None = prefetched_activities
    if not activities_list:
        stmt = select(activity_models.Activity).where(activity_models.Activity.id.in_(activity_ids))
        activities_list = db.scalars(stmt).all()

    if not activities_list:
        return []

    allowed_ids = [activity.id for activity in activities_list if activity.user_id == token_user_id]

    if not allowed_ids:
        return []

    laps_stmt = select(activity_laps_models.ActivityLaps).where(
        activity_laps_models.ActivityLaps.activity_id.in_(allowed_ids)
    )
    activity_laps = db.scalars(laps_stmt).all()

    if not activity_laps:
        return []

    return [_to_read_schema(lap) for lap in activity_laps]


@core_decorators.handle_db_errors
def get_public_activity_laps(
    activity_id: int,
    db: Session,
) -> list[activity_laps_schema.ActivityLapsRead] | None:
    """
    Retrieve public activity laps for an activity.

    Args:
        activity_id: The activity ID.
        db: Database session.

    Returns:
        List of ActivityLapsRead or None if not
            found, hidden, or not publicly visible.

    Raises:
        HTTPException: If database error occurs.
    """
    activity = activity_crud.get_public_activity_for_child_read(activity_id, db, hide_attr="hide_laps")

    if not activity:
        return None

    stmt = select(activity_laps_models.ActivityLaps).where(
        activity_laps_models.ActivityLaps.activity_id == activity_id,
    )
    activity_laps = db.scalars(stmt).all()

    if not activity_laps:
        return None

    return [_to_read_schema(lap) for lap in activity_laps]


@core_decorators.handle_db_errors
def create_activity_laps(
    activity_laps: list[dict],
    activity_id: int,
    db: Session,
    *,
    commit: bool = True,
) -> None:
    """
    Bulk create activity laps for an activity.

    Args:
        activity_laps: List of lap dicts from
            file parsers.
        activity_id: The parent activity ID.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException: If database error occurs.
    """
    laps = [
        activity_laps_models.ActivityLaps(
            activity_id=activity_id,
            **{key: lap.get(key) for key in _LAP_COLUMNS},
        )
        for lap in activity_laps
    ]

    db.add_all(laps)
    # commit=False keeps the laps in the caller's open transaction (atomic ingestion).
    if commit:
        db.commit()
    else:
        db.flush()

    core_logger.print_to_log(
        f"Created {len(laps)} lap(s) for activity {activity_id}",
        "debug",
    )
