"""Activity workout steps CRUD operations."""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.logger as core_logger
import modules.activities.activity.models as activity_models
import modules.activities.activity_workout_steps.models as activity_workout_steps_models
import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema

logger = core_logger.get_logger(__name__)


def _to_read_schema(
    orm_step: activity_workout_steps_models.ActivityWorkoutSteps,
) -> activity_workout_steps_schema.ActivityWorkoutSteps:
    """Convert an ORM row to its read schema so ORM never leaves ``crud``."""
    return activity_workout_steps_schema.ActivityWorkoutSteps.model_validate(orm_step)


@core_decorators.handle_db_errors
def get_activity_workout_steps(
    activity_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = 200,
) -> list[activity_workout_steps_schema.ActivityWorkoutSteps]:
    """
    Get one page of an activity's planned workout steps, in step order.

    Performs no access check: whether the caller may read these rows is decided
    by :mod:`modules.activities.activity_workout_steps.service`.

    Args:
        activity_id: Activity ID to fetch steps for.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.

    Returns:
        The page of workout steps, empty when the activity has none.

    Raises:
        ProcessingError: If database error occurs.
    """
    stmt = (
        select(activity_workout_steps_models.ActivityWorkoutSteps)
        .where(activity_workout_steps_models.ActivityWorkoutSteps.activity_id == activity_id)
        .order_by(activity_workout_steps_models.ActivityWorkoutSteps.id)
        .offset((page_number - 1) * num_records)
        .limit(num_records)
    )
    workout_steps = db.scalars(stmt).all()

    return [_to_read_schema(step) for step in workout_steps]


@core_decorators.handle_db_errors
def count_activity_workout_steps(activity_id: int, db: Session) -> int:
    """
    Count an activity's planned workout steps.

    Args:
        activity_id: Activity ID to count steps for.
        db: Database session.

    Returns:
        The total number of workout steps.

    Raises:
        ProcessingError: If database error occurs.
    """
    stmt = select(func.count()).select_from(
        select(activity_workout_steps_models.ActivityWorkoutSteps.id)
        .where(activity_workout_steps_models.ActivityWorkoutSteps.activity_id == activity_id)
        .subquery()
    )
    return db.scalar(stmt) or 0


@core_decorators.handle_db_errors
def get_activities_workout_steps(
    activity_ids: list[int],
    token_user_id: int,
    db: Session,
    activities: Sequence[activity_models.Activity] | None = None,
) -> list[activity_workout_steps_schema.ActivityWorkoutSteps]:
    """
    Get workout steps for multiple activities.

    Args:
        activity_ids: List of activity IDs.
        token_user_id: Authenticated user ID.
        db: Database session.
        activities: Pre-fetched Activity ORM
            instances (optional).

    Returns:
        List of workout steps (may be empty).

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

    allowed_ids = [
        activity.id
        for activity in activities
        if (activity.user_id == token_user_id or not activity.hide_workout_sets_steps)
    ]

    if not allowed_ids:
        return []

    steps_stmt = select(activity_workout_steps_models.ActivityWorkoutSteps).where(
        activity_workout_steps_models.ActivityWorkoutSteps.activity_id.in_(allowed_ids)
    )
    workout_steps = list(db.scalars(steps_stmt).all())

    if not workout_steps:
        return []

    return [_to_read_schema(step) for step in workout_steps]


@core_decorators.handle_db_errors
def create_activity_workout_steps(
    activity_workout_steps: list[activity_workout_steps_schema.ActivityWorkoutSteps],
    activity_id: int,
    db: Session,
    *,
    commit: bool = True,
) -> None:
    """
    Bulk create workout steps for an activity.

    Args:
        activity_workout_steps: List of workout step
            schemas to persist.
        activity_id: Activity ID to associate with.
        db: Database session.

    Returns:
        None.

    Raises:
        ProcessingError: If database error occurs.
    """
    workout_steps = [
        activity_workout_steps_models.ActivityWorkoutSteps(
            activity_id=activity_id,
            message_index=step.message_index,
            duration_type=step.duration_type,
            duration_value=step.duration_value,
            target_type=step.target_type,
            target_value=step.target_value,
            intensity=step.intensity,
            notes=step.notes,
            exercise_category=(step.exercise_category),
            exercise_name=step.exercise_name,
            exercise_weight=(step.exercise_weight),
            weight_display_unit=(step.weight_display_unit),
            secondary_target_value=(step.secondary_target_value),
        )
        for step in activity_workout_steps
    ]

    db.add_all(workout_steps)
    # commit=False keeps the steps in the caller's open transaction (atomic ingestion).
    if commit:
        db.commit()
    else:
        db.flush()

    logger.debug(
        "Created activity workout steps",
        extra=core_logger.context(activity_id=activity_id, count=len(workout_steps)),
    )
