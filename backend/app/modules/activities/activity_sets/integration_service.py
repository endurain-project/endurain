"""Public persistence operations for activity workout sets."""

from sqlalchemy.orm import Session

import modules.activities.activity_sets.crud as activity_sets_crud
import modules.activities.activity_sets.schema as activity_sets_schema


def list_sets_for_activities(
    activity_ids: list[int],
    db: Session,
) -> list[activity_sets_schema.ActivitySetsRead]:
    """Return workout sets for activity IDs already scoped by the caller."""
    return activity_sets_crud.get_activities_sets(activity_ids, db)


def store_sets(
    sets: list[activity_sets_schema.ActivitySetsCreate | list],
    activity_id: int,
    db: Session,
    *,
    commit: bool = True,
) -> None:
    """Store parsed workout sets for an activity."""
    activity_sets_crud.create_activity_sets(sets, activity_id, db, commit=commit)
