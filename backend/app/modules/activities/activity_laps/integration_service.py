"""Public persistence operations for activity laps."""

from sqlalchemy.orm import Session

import modules.activities.activity_laps.crud as activity_laps_crud
import modules.activities.activity_laps.schema as activity_laps_schema


def list_laps_for_activities(
    activity_ids: list[int],
    db: Session,
) -> list[activity_laps_schema.ActivityLapsRead]:
    """Return laps for activity IDs already scoped by the caller."""
    return activity_laps_crud.get_activities_laps(activity_ids, db)


def store_laps(
    laps: list[dict],
    activity_id: int,
    db: Session,
    *,
    commit: bool = True,
) -> None:
    """Store parsed laps for an activity."""
    activity_laps_crud.create_activity_laps(laps, activity_id, db, commit=commit)
