"""The workout-set operations exposed only to data migrations."""

from collections.abc import Sequence

from sqlalchemy.orm import Session

import modules.activities.activity_sets.contracts as activity_sets_contracts
import modules.activities.activity_sets.crud as activity_sets_crud


def create_activity_sets(
    activity_sets: Sequence[activity_sets_contracts.ActivitySetsCreate | list[object]],
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
