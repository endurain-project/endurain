"""The operations other modules may call on health weight records.

The writes stage; the caller owns the unit of work and commits.
"""

import uuid
from datetime import date, datetime

from sqlalchemy.orm import Session

import core.sync as core_sync
import modules.health.health_weight.crud as health_weight_crud
import modules.health.health_weight.schema as health_weight_schema
import modules.health.health_weight.service as health_weight_service
import modules.health.record_crud as health_record_crud
import modules.users.users_profile.contracts as users_profile_contracts


def get_latest_health_weight(
    user_id: uuid.UUID, on_or_before: date, db: Session
) -> health_weight_schema.HealthWeightRead | None:
    """Return a user's most recent weight record dated no later than a day, or ``None``.

    Args:
        user_id: The record's owner.
        on_or_before: The last day a record may be dated, the user's today.
        db: Database session.

    Returns:
        The latest record, or ``None``.
    """
    return health_weight_crud.get_latest_weight_by_user_id(user_id, on_or_before, db)


def get_health_weight_by_date(
    user_id: uuid.UUID, date: str, db: Session
) -> health_weight_schema.HealthWeightRead | None:
    """Return a user's weight record for a date, or ``None``.

    Args:
        user_id: The record's owner.
        date: The record's date.
        db: Database session.

    Returns:
        The record, or ``None``.
    """
    return health_weight_crud.get_health_weight_by_date_and_user_id(user_id, date, db)


def upsert_health_weight(
    user_id: uuid.UUID, health_weight: health_weight_schema.HealthWeightImport, db: Session
) -> health_weight_schema.HealthWeightRead:
    """Stage a weight record for a user, or an update to their record for the same date.

    Args:
        user_id: The record's owner.
        health_weight: The record to store.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the date's record cannot be created or found.
    """
    return health_weight_service.stage_upsert_health_weight(user_id, health_weight, db)


def recalculate_bmi_for_user(user_id: uuid.UUID, height_cm: float | None, db: Session) -> None:
    """Stage a BMI recalculation for a user's manually entered weight records.

    Provider records keep the BMI the provider reported.

    Args:
        user_id: The records' owner.
        height_cm: The user's height in centimeters, or ``None`` if unknown.
        db: Database session.
    """
    health_weight_crud.recalculate_bmi_for_user(user_id, height_cm, db)


def profile_section() -> users_profile_contracts.ProfileRecordsSection:
    """Return the weight records' section of a profile export and import.

    Returns:
        The section, which exports a user's weight records and stages the archived ones.
    """
    return users_profile_contracts.ProfileRecordsSection(
        key="health_weight",
        export=health_weight_crud.get_all_health_weight_by_user_id,
        restore=health_weight_service.restore_profile_records,
    )


def list_changed_health_weight(
    user_id: uuid.UUID, after: core_sync.Position[uuid.UUID] | None, until: datetime, limit: int, db: Session
) -> list[health_weight_schema.HealthWeightRead]:
    """Return a user's weight records changed after a position, oldest change first.

    Args:
        user_id: The records' owner.
        after: Return records strictly after this ``(updated_at, id)``; ``None`` from the first.
        until: Return only records changed before this instant.
        limit: The most records to return.
        db: Database session.

    Returns:
        The records, in ``(updated_at, id)`` order.
    """
    return health_weight_crud.list_changed(user_id, after, until, limit, db)


def list_health_weight_deletions(
    user_id: uuid.UUID, after: core_sync.Position[uuid.UUID] | None, until: datetime, limit: int, db: Session
) -> list[core_sync.Deletion[uuid.UUID]]:
    """Return a user's deleted weight records after a position, oldest deletion first.

    Args:
        user_id: The records' owner.
        after: Return deletions strictly after this ``(deleted_at, id)``; ``None`` from the first.
        until: Return only deletions before this instant.
        limit: The most deletions to return.
        db: Database session.

    Returns:
        The deletions, in ``(deleted_at, id)`` order.
    """
    return health_record_crud.list_deletions(health_weight_crud.SPEC.sync_type, user_id, after, until, limit, db)
