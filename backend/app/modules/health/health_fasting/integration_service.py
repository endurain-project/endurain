"""The operations other modules may call on health fasting records."""

from sqlalchemy.orm import Session

import modules.health.health_fasting.crud as health_fasting_crud
import modules.health.health_fasting.schema as health_fasting_schema


def get_active_fasting(user_id: int, db: Session) -> health_fasting_schema.HealthFastingRead | None:
    """Return a user's in-progress fasting session, or ``None``.

    Args:
        user_id: The session's owner.
        db: Database session.

    Returns:
        The active session, or ``None``.
    """
    return health_fasting_crud.get_active_fasting_by_user_id(user_id, db)
