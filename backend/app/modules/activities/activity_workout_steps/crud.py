"""Activity workout steps CRUD operations."""

from sqlalchemy import select
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.logger as core_logger
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.models as activity_models
import modules.activities.activity_workout_steps.models as activity_workout_steps_models
import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema
import modules.server_settings.utils as server_settings_utils


def _to_read_schema(
    orm_step: activity_workout_steps_models.ActivityWorkoutSteps,
) -> activity_workout_steps_schema.ActivityWorkoutSteps:
    """Convert an ORM row to its read schema so ORM never leaves ``crud``."""
    return activity_workout_steps_schema.ActivityWorkoutSteps.model_validate(orm_step)


@core_decorators.handle_db_errors
def get_activity_workout_steps(
    activity_id: int,
    token_user_id: int,
    db: Session,
) -> list[activity_workout_steps_schema.ActivityWorkoutSteps] | None:
    """
    Get workout steps for a single activity.

    Args:
        activity_id: Activity ID to fetch steps for.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        List of workout steps or None if not found
        or access denied.

    Raises:
        HTTPException: If database error occurs.
    """
    activity = activity_crud.get_activity_by_id(activity_id, db)

    if not activity:
        return None

    if token_user_id != activity.user_id and activity.hide_workout_sets_steps:
        return None

    stmt = select(activity_workout_steps_models.ActivityWorkoutSteps).where(
        activity_workout_steps_models.ActivityWorkoutSteps.activity_id == activity_id,
    )
    workout_steps = db.scalars(stmt).all()

    if not workout_steps:
        return None

    return [_to_read_schema(step) for step in workout_steps]


@core_decorators.handle_db_errors
def get_activities_workout_steps(
    activity_ids: list[int],
    token_user_id: int,
    db: Session,
    activities: (list[activity_models.Activity] | None) = None,
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
        HTTPException: If database error occurs.
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
def get_public_activity_workout_steps(
    activity_id: int,
    db: Session,
) -> list[activity_workout_steps_schema.ActivityWorkoutSteps] | None:
    """
    Get workout steps for a public activity.

    Args:
        activity_id: Activity ID to fetch steps for.
        db: Database session.

    Returns:
        List of workout steps or None if not found,
        hidden, not public, or feature disabled.

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

    stmt = select(activity_workout_steps_models.ActivityWorkoutSteps).where(
        activity_workout_steps_models.ActivityWorkoutSteps.activity_id == activity_id,
    )
    workout_steps = list(db.scalars(stmt).all())

    if not workout_steps:
        return None

    return [_to_read_schema(step) for step in workout_steps]


@core_decorators.handle_db_errors
def create_activity_workout_steps(
    activity_workout_steps: list[activity_workout_steps_schema.ActivityWorkoutSteps],
    activity_id: int,
    db: Session,
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
        HTTPException: If database error occurs.
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
    db.commit()

    core_logger.print_to_log(
        f"Created {len(workout_steps)} workout step(s) for activity {activity_id}",
        "debug",
    )
