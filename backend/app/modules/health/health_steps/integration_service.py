"""The operations other modules may call on health steps records.

The writes stage; the caller owns the unit of work and commits.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

import core.sync as core_sync
import modules.health.health_steps.crud as health_steps_crud
import modules.health.health_steps.schema as health_steps_schema
import modules.health.health_steps.service as health_steps_service
import modules.health.record_crud as health_record_crud
import modules.users.users_profile.contracts as users_profile_contracts


def get_health_steps_by_date(user_id: uuid.UUID, date: str, db: Session) -> health_steps_schema.HealthStepsRead | None:
    """Return a user's steps record for a date, or ``None``.

    Args:
        user_id: The record's owner.
        date: The record's date.
        db: Database session.

    Returns:
        The record, or ``None``.
    """
    return health_steps_crud.get_health_steps_by_date_and_user_id(user_id, date, db)


def upsert_health_steps(
    user_id: uuid.UUID, health_steps: health_steps_schema.HealthStepsImport, db: Session
) -> health_steps_schema.HealthStepsRead:
    """Stage a steps record for a user, or an update to their record for the same date.

    Args:
        user_id: The record's owner.
        health_steps: The record to store.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the date's record cannot be created or found.
    """
    return health_steps_service.stage_upsert_health_steps(user_id, health_steps, db)


def profile_section() -> users_profile_contracts.ProfileRecordsSection:
    """Return the steps records' section of a profile export and import.

    Returns:
        The section, which exports a user's steps records and stages the archived ones.
    """
    return users_profile_contracts.ProfileRecordsSection(
        key="health_steps",
        export=health_steps_crud.get_health_steps_by_user_id,
        restore=health_steps_service.restore_profile_records,
    )


def list_changed_health_steps(
    user_id: uuid.UUID, after: core_sync.Position[uuid.UUID] | None, until: datetime, limit: int, db: Session
) -> list[health_steps_schema.HealthStepsRead]:
    """Return a user's steps records changed after a position, oldest change first.

    Args:
        user_id: The records' owner.
        after: Return records strictly after this ``(updated_at, id)``; ``None`` from the first.
        until: Return only records changed before this instant.
        limit: The most records to return.
        db: Database session.

    Returns:
        The records, in ``(updated_at, id)`` order.
    """
    return health_steps_crud.list_changed(user_id, after, until, limit, db)


def list_health_steps_deletions(
    user_id: uuid.UUID, after: core_sync.Position[uuid.UUID] | None, until: datetime, limit: int, db: Session
) -> list[core_sync.Deletion[uuid.UUID]]:
    """Return a user's deleted steps records after a position, oldest deletion first.

    Args:
        user_id: The records' owner.
        after: Return deletions strictly after this ``(deleted_at, id)``; ``None`` from the first.
        until: Return only deletions before this instant.
        limit: The most deletions to return.
        db: Database session.

    Returns:
        The deletions, in ``(deleted_at, id)`` order.
    """
    return health_record_crud.list_deletions(health_steps_crud.SPEC.sync_type, user_id, after, until, limit, db)
