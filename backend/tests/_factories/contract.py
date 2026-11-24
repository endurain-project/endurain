"""Rows the HTTP contract and audit tests need that no other factory makes."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.schema as activity_schema


def make_activity(db: Session, user_id: uuid.UUID, **overrides: object) -> activity_schema.ActivityRead:
    """Stage an activity through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        user_id: The activity's owner.
        **overrides: Field values of :class:`~modules.activities.activity.contracts.ActivityCore`, which replace the
            defaults of a one-hour activity that started two hours ago with nothing hidden.

    Returns:
        The staged activity.
    """
    start = datetime.now(UTC) - timedelta(hours=2)
    values: dict[str, object] = {
        "user_id": user_id,
        "name": "Morning run",
        "activity_type": 1,
        "start_time": start,
        "end_time": start + timedelta(hours=1),
        "distance": 10000,
        "total_elapsed_time": 3600,
        "total_timer_time": 3600,
    }
    values.update({name: False for name in activity_schema.ActivityFields.model_fields if name.startswith("hide_")})
    values.update(overrides)
    return activity_crud.create_activity(activity_contracts.ActivityCore.model_validate(values), db)
