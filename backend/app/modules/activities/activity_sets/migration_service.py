"""The workout-set operations exposed only to data migrations."""

from sqlalchemy.orm import Session

import modules.activities.activity_sets.contracts as activity_sets_contracts
import modules.activities.activity_sets.crud as activity_sets_crud


def create_activity_sets(
    activity_sets: list[activity_sets_contracts.ActivitySetsCreate | list],
    activity_id: int,
    db: Session,
) -> None:
    """Create workout sets for an activity and commit them, as migrations did.

    Args:
        activity_sets: Sets to store.
        activity_id: The parent activity ID.
        db: Database session.
    """
    activity_sets_crud.create_activity_sets(activity_sets, activity_id, db)
    db.commit()
