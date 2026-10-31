"""Activity workout steps CRUD operations."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import modules.activities.activity_workout_steps.contracts as activity_workout_steps_contracts
import modules.activities.activity_workout_steps.models as activity_workout_steps_models
import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema
import modules.activities.activity_workout_steps.serializers as activity_workout_steps_serializers


def get_activity_workout_steps(
    activity_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = 200,
) -> list[activity_workout_steps_schema.ActivityWorkoutStepsRead]:
    """Get one page of an activity's planned workout steps, in step order.

    Performs no access check: whether the caller may read these rows is decided
    by :mod:`modules.activities.activity_workout_steps.service`.

    Args:
        activity_id: Activity ID to fetch steps for.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.

    Returns:
        The page of workout steps, empty when the activity has none.
    """
    stmt = (
        select(activity_workout_steps_models.ActivityWorkoutSteps)
        .where(activity_workout_steps_models.ActivityWorkoutSteps.activity_id == activity_id)
        .order_by(activity_workout_steps_models.ActivityWorkoutSteps.id)
        .offset((page_number - 1) * num_records)
        .limit(num_records)
    )
    workout_steps = db.scalars(stmt).all()

    return [activity_workout_steps_serializers.to_read_schema(step) for step in workout_steps]


def count_activity_workout_steps(activity_id: int, db: Session) -> int:
    """Count an activity's planned workout steps.

    Args:
        activity_id: Activity ID to count steps for.
        db: Database session.

    Returns:
        The total number of workout steps.
    """
    stmt = select(func.count()).select_from(
        select(activity_workout_steps_models.ActivityWorkoutSteps.id)
        .where(activity_workout_steps_models.ActivityWorkoutSteps.activity_id == activity_id)
        .subquery()
    )
    return db.scalar(stmt) or 0


def get_activities_workout_steps(
    activity_ids: list[int],
    db: Session,
) -> list[activity_workout_steps_schema.ActivityWorkoutStepsRead]:
    """Retrieve the workout steps of several activities at once.

    Performs no access check and joins no parent row: which activities the
    caller may read is decided before this is reached, by the activities
    integration service that owns them.

    Args:
        activity_ids: The activities to read, already scoped to the caller.
        db: Database session.

    Returns:
        The workout steps of those activities, empty when there are none.
    """
    if not activity_ids:
        return []

    stmt = select(activity_workout_steps_models.ActivityWorkoutSteps).where(
        activity_workout_steps_models.ActivityWorkoutSteps.activity_id.in_(activity_ids)
    )
    return [activity_workout_steps_serializers.to_read_schema(row) for row in db.scalars(stmt).all()]


def create_activity_workout_steps(
    activity_workout_steps: list[activity_workout_steps_contracts.ActivityWorkoutStepsCreate],
    activity_id: int,
    db: Session,
) -> None:
    """Stage workout steps for an activity (flushed, not committed).

    Args:
        activity_workout_steps: List of workout step
            schemas to persist.
        activity_id: Activity ID to associate with.
        db: Database session.
    """
    workout_steps = [activity_workout_steps_serializers.to_orm(step, activity_id) for step in activity_workout_steps]

    db.add_all(workout_steps)
    db.flush()
