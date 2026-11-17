"""The operations other modules may call on health sleep records.

The writes stage; the caller owns the unit of work and commits. Records arrive
already scored by their provider, so nothing here scores them.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

import core.sync as core_sync
import modules.health.health_sleep.crud as health_sleep_crud
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.health_sleep.service as health_sleep_service
import modules.health.record_crud as health_record_crud
import modules.users.users_profile.contracts as users_profile_contracts


def get_health_sleep_by_date(user_id: uuid.UUID, date: str, db: Session) -> health_sleep_schema.HealthSleepRead | None:
    """Return a user's sleep record for a date, or ``None``.

    Args:
        user_id: The record's owner.
        date: The record's date.
        db: Database session.

    Returns:
        The record, or ``None``.
    """
    return health_sleep_crud.get_health_sleep_by_date_and_user_id(user_id, date, db)


def upsert_health_sleep(
    user_id: uuid.UUID, health_sleep: health_sleep_schema.HealthSleepImport, db: Session
) -> health_sleep_schema.HealthSleepRead:
    """Stage a sleep record for a user, or an update to their record for the same date.

    Args:
        user_id: The record's owner.
        health_sleep: The record to store.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the date's record cannot be created or found.
    """
    return health_sleep_service.stage_upsert_health_sleep(user_id, health_sleep, db)


def profile_section() -> users_profile_contracts.ProfileRecordsSection:
    """Return the sleep records' section of a profile export and import.

    Returns:
        The section, which exports a user's sleep records and stages the archived ones.
    """
    return users_profile_contracts.ProfileRecordsSection(
        key="health_sleep",
        export=health_sleep_crud.get_health_sleep_by_user_id,
        restore=health_sleep_service.restore_profile_records,
    )


def list_changed_health_sleep(
    user_id: uuid.UUID, after: core_sync.Position | None, until: datetime, limit: int, db: Session
) -> list[health_sleep_schema.HealthSleepRead]:
    """Return a user's sleep records (with their stages) changed after a position, oldest change first.

    Args:
        user_id: The records' owner.
        after: Return records strictly after this ``(updated_at, id)``; ``None`` from the first.
        until: Return only records changed before this instant.
        limit: The most records to return.
        db: Database session.

    Returns:
        The records, in ``(updated_at, id)`` order.
    """
    return health_sleep_crud.list_changed(user_id, after, until, limit, db)


def list_health_sleep_deletions(
    user_id: uuid.UUID, after: core_sync.Position | None, until: datetime, limit: int, db: Session
) -> list[core_sync.Deletion]:
    """Return a user's deleted sleep records (with their stages) after a position, oldest deletion first.

    Args:
        user_id: The records' owner.
        after: Return deletions strictly after this ``(deleted_at, id)``; ``None`` from the first.
        until: Return only deletions before this instant.
        limit: The most deletions to return.
        db: Database session.

    Returns:
        The deletions, in ``(deleted_at, id)`` order.
    """
    return health_record_crud.list_deletions(health_sleep_crud.SPEC.sync_type, user_id, after, until, limit, db)
