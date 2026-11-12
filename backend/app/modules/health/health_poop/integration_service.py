"""The operations other modules may call on health poop records.

The writes stage; the caller owns the unit of work and commits.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

import core.sync as core_sync
import modules.health.health_poop.crud as health_poop_crud
import modules.health.health_poop.schema as health_poop_schema
import modules.health.health_poop.service as health_poop_service
import modules.health.record_crud as health_record_crud
import modules.users.users_profile.contracts as users_profile_contracts


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


def profile_section() -> users_profile_contracts.ProfileRecordsSection:
    """Return the poop records' section of a profile export and import.

    Returns:
        The section, which exports a user's poop records and stages the archived ones.
    """
    return users_profile_contracts.ProfileRecordsSection(
        key="health_poop",
        export=health_poop_crud.get_health_poop_by_user_id,
        restore=health_poop_service.restore_profile_records,
    )


def list_changed_health_poop(
    user_id: int, after: core_sync.Position[uuid.UUID] | None, until: datetime, limit: int, db: Session
) -> list[health_poop_schema.HealthPoopRead]:
    """Return a user's poop records changed after a position, oldest change first.

    Args:
        user_id: The records' owner.
        after: Return records strictly after this ``(updated_at, id)``; ``None`` from the first.
        until: Return only records changed before this instant.
        limit: The most records to return.
        db: Database session.

    Returns:
        The records, in ``(updated_at, id)`` order.
    """
    return health_poop_crud.list_changed(user_id, after, until, limit, db)


def list_health_poop_deletions(
    user_id: int, after: core_sync.Position[uuid.UUID] | None, until: datetime, limit: int, db: Session
) -> list[core_sync.Deletion[uuid.UUID]]:
    """Return a user's deleted poop records after a position, oldest deletion first.

    Args:
        user_id: The records' owner.
        after: Return deletions strictly after this ``(deleted_at, id)``; ``None`` from the first.
        until: Return only deletions before this instant.
        limit: The most deletions to return.
        db: Database session.

    Returns:
        The deletions, in ``(deleted_at, id)`` order.
    """
    return health_record_crud.list_deletions(health_poop_crud.SPEC.sync_type, user_id, after, until, limit, db)
