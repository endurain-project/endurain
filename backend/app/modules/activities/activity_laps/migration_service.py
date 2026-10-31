"""The lap operations exposed only to data migrations."""

from sqlalchemy.orm import Session

import modules.activities.activity_laps.crud as activity_laps_crud


def create_activity_laps(activity_laps: list[dict], activity_id: int, db: Session) -> None:
    """Create laps for an activity and commit them, as migrations did.

    Args:
        activity_laps: Lap dicts to store.
        activity_id: The parent activity ID.
        db: Database session.
    """
    activity_laps_crud.create_activity_laps(activity_laps, activity_id, db)
    db.commit()
