"""Module surface for activity workout steps: ingestion and profile contributors."""

from typing import Any

from sqlalchemy.orm import Session

import modules.activities.activity_workout_steps.contracts as activity_workout_steps_contracts
import modules.activities.activity_workout_steps.crud as activity_workout_steps_crud
import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema
import modules.activities.contributors as activities_contributors


def _list_workout_steps_for_activities(
    activity_ids: list[int],
    db: Session,
) -> list[activity_workout_steps_schema.ActivityWorkoutStepsRead]:
    """Return workout steps for activity IDs already scoped by the caller.

    Args:
        activity_ids: IDs of the activities to read.
        db: Database session.

    Returns:
        Workout steps for activity IDs already scoped by the caller.
    """
    return activity_workout_steps_crud.get_activities_workout_steps(activity_ids, db)


def _store_workout_steps(
    steps: list[activity_workout_steps_contracts.ActivityWorkoutStepsCreate],
    activity_id: int,
    db: Session,
) -> None:
    """Store parsed workout steps for an activity.

    Args:
        steps: Workout steps to store.
        activity_id: ID of the parent activity.
        db: Database session.
    """
    activity_workout_steps_crud.create_activity_workout_steps(steps, activity_id, db)


def _parse_profile_record(
    record: dict[str, Any], _activity_id: int
) -> activity_workout_steps_contracts.ActivityWorkoutStepsCreate:
    """Validate one archived workout step.

    Steps are stored from a parent-less shape, so the archived ``activity_id`` is
    dropped rather than re-keyed.

    Args:
        record: The archived record, without its ``id``.
        _activity_id: ID of the restored activity (unused: the store re-keys steps).

    Returns:
        The validated step.
    """
    data = {key: value for key, value in record.items() if key != "activity_id"}
    return activity_workout_steps_contracts.ActivityWorkoutStepsCreate.model_validate(data)


def ingestion_contributor() -> activities_contributors.ActivityIngestionContributor:
    """Return the workout-step ingestion contribution.

    Returns:
        The contributor.
    """
    return activities_contributors.child_ingestion_contributor(key="workout_steps", store=_store_workout_steps)


def profile_contributor() -> activities_contributors.ProfileActivityContributor:
    """Return the workout-step profile contribution.

    Returns:
        The contributor.
    """
    return activities_contributors.child_profile_contributor(
        key="workout_steps",
        archive_path="data/activity_workout_steps.json",
        count_key="activity_workout_steps",
        split=False,
        export=_list_workout_steps_for_activities,
        store=_store_workout_steps,
        parse_record=_parse_profile_record,
    )
