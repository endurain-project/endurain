"""The operations other modules may call on health fasting records.

The writes stage; the caller owns the unit of work and commits.
"""

from sqlalchemy.orm import Session

import modules.health.health_fasting.crud as health_fasting_crud
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.health_fasting.service as health_fasting_service


def get_active_fasting(user_id: int, db: Session) -> health_fasting_schema.HealthFastingRead | None:
    """Return a user's in-progress fasting session, or ``None``.

    Args:
        user_id: The session's owner.
        db: Database session.

    Returns:
        The active session, or ``None``.
    """
    return health_fasting_crud.get_active_fasting_by_user_id(user_id, db)


def list_health_fasting(user_id: int, db: Session) -> list[health_fasting_schema.HealthFastingRead]:
    """Return all of a user's fasting records, newest first.

    Args:
        user_id: The records' owner.
        db: Database session.

    Returns:
        The records.
    """
    return health_fasting_crud.get_health_fasting_by_user_id(user_id, db)


def import_health_fasting(user_id: int, health_fasting: health_fasting_schema.HealthFastingCreate, db: Session) -> bool:
    """Stage a fasting session for a user unless they already have it.

    Args:
        user_id: The session's owner.
        health_fasting: The session to import.
        db: Database session.

    Returns:
        True when the session was staged, False when it was skipped.
    """
    return health_fasting_service.stage_import_health_fasting(user_id, health_fasting, db)
