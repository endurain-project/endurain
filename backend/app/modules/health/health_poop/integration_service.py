"""The operations other modules may call on health poop records.

The writes stage; the caller owns the unit of work and commits.
"""

from sqlalchemy.orm import Session

import modules.health.health_poop.crud as health_poop_crud
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


def list_health_poop(user_id: int, db: Session) -> list[health_poop_schema.HealthPoopRead]:
    """Return all of a user's poop records, newest first.

    Args:
        user_id: The records' owner.
        db: Database session.

    Returns:
        The records.
    """
    return health_poop_crud.get_health_poop_by_user_id(user_id, db)


def import_health_poop(user_id: int, health_poop: health_poop_schema.HealthPoopCreate, db: Session) -> bool:
    """Stage a poop record for a user unless they already have one at that time.

    Args:
        user_id: The record's owner.
        health_poop: The record to import.
        db: Database session.

    Returns:
        True when the record was staged, False when it was skipped.
    """
    return health_poop_service.stage_import_health_poop(user_id, health_poop, db)
