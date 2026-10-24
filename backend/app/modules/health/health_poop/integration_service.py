"""The operations other modules may call on health poop records."""

from sqlalchemy.orm import Session

import modules.health.health_poop.schema as health_poop_schema
import modules.health.health_poop.service as health_poop_service


def list_health_poop_by_date(user_id: int, date: str, db: Session) -> list[health_poop_schema.HealthPoopRead]:
    """Return a user's poop records for a calendar date in their own timezone.

    Args:
        user_id: The records' owner.
        date: The calendar date.
        db: Database session.

    Returns:
        The records of that date, newest first.
    """
    return health_poop_service.list_health_poop_by_date(user_id, date, db)
