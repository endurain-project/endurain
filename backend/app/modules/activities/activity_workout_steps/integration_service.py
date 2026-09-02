"""Public persistence operations for activity workout steps."""

from typing import Any

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_workout_steps.crud as workout_steps_crud
import modules.activities.activity_workout_steps.schema as workout_steps_schema
import modules.activities.contributors as activity_contributors


def _list_workout_steps_for_activities(
    activity_ids: list[int],
    db: Session,
) -> list[workout_steps_schema.ActivityWorkoutSteps]:
    """Return workout steps for activity IDs already scoped by the caller."""
    return workout_steps_crud.get_activities_workout_steps(activity_ids, db)


def _store_workout_steps(
    steps: list[workout_steps_schema.ActivityWorkoutSteps],
    activity_id: int,
    db: Session,
    *,
    commit: bool = True,
) -> None:
    """Store parsed workout steps for an activity."""
    workout_steps_crud.create_activity_workout_steps(steps, activity_id, db, commit=commit)


def _persist_ingestion_component(
    data: Any,
    activity: activity_schema.Activity,
    db: Session,
    *,
    commit: bool,
) -> None:
    """Persist parsed workout steps through the ingestion contract."""
    if activity.id is None:
        raise core_exceptions.ProcessingError("Cannot store workout steps before the activity has an id")
    _store_workout_steps(data, activity.id, db, commit=commit)


def ingestion_contributor() -> activity_contributors.ActivityIngestionContributor:
    """Return the workout-step ingestion contribution."""
    return activity_contributors.ActivityIngestionContributor(
        key="workout_steps",
        persist=_persist_ingestion_component,
    )


def _restore_profile_records(
    records: list[dict[str, Any]],
    original_activity_id: int,
    new_activity: activity_schema.Activity,
    db: Session,
) -> int:
    """Validate and restore profile workout steps for one activity."""
    if new_activity.id is None:
        return 0

    steps: list[workout_steps_schema.ActivityWorkoutSteps] = []
    for record in records:
        if record.get("activity_id") != original_activity_id:
            continue
        data = dict(record)
        data.pop("id", None)
        data["activity_id"] = new_activity.id
        steps.append(workout_steps_schema.ActivityWorkoutSteps.model_validate(data))

    if steps:
        _store_workout_steps(steps, new_activity.id, db)
    return len(steps)


def profile_contributor() -> activity_contributors.ProfileActivityContributor:
    """Return the workout-step profile contribution."""
    return activity_contributors.ProfileActivityContributor(
        key="workout_steps",
        archive_path="data/activity_workout_steps.json",
        count_key="activity_workout_steps",
        split=False,
        export=_list_workout_steps_for_activities,
        restore=_restore_profile_records,
    )
