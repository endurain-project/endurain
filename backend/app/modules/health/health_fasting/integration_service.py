"""The operations other modules may call on health fasting records.

The writes stage; the caller owns the unit of work and commits.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

import core.sync as core_sync
import modules.health.health_fasting.crud as health_fasting_crud
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.health_fasting.service as health_fasting_service
import modules.health.record_crud as health_record_crud
import modules.users.users_profile.contracts as users_profile_contracts


def get_active_fasting(user_id: uuid.UUID, db: Session) -> health_fasting_schema.HealthFastingRead | None:
    """Return a user's in-progress fasting session, or ``None``.

    Args:
        user_id: The session's owner.
        db: Database session.

    Returns:
        The active session, or ``None``.
    """
    return health_fasting_crud.get_active_fasting_by_user_id(user_id, db)


def profile_section() -> users_profile_contracts.ProfileRecordsSection:
    """Return the fasting records' section of a profile export and import.

    Returns:
        The section, which exports a user's fasting records and stages the archived ones.
    """
    return users_profile_contracts.ProfileRecordsSection(
        key="health_fasting",
        export=health_fasting_crud.get_health_fasting_by_user_id,
        restore=health_fasting_service.restore_profile_records,
    )


def list_changed_health_fasting(
    user_id: uuid.UUID, after: core_sync.Position | None, until: datetime, limit: int, db: Session
) -> list[health_fasting_schema.HealthFastingRead]:
    """Return a user's fasting records changed after a position, oldest change first.

    Args:
        user_id: The records' owner.
        after: Return records strictly after this ``(updated_at, id)``; ``None`` from the first.
        until: Return only records changed before this instant.
        limit: The most records to return.
        db: Database session.

    Returns:
        The records, in ``(updated_at, id)`` order.
    """
    return health_fasting_crud.list_changed(user_id, after, until, limit, db)


def list_health_fasting_deletions(
    user_id: uuid.UUID, after: core_sync.Position | None, until: datetime, limit: int, db: Session
) -> list[core_sync.Deletion]:
    """Return a user's deleted fasting records after a position, oldest deletion first.

    Args:
        user_id: The records' owner.
        after: Return deletions strictly after this ``(deleted_at, id)``; ``None`` from the first.
        until: Return only deletions before this instant.
        limit: The most deletions to return.
        db: Database session.

    Returns:
        The deletions, in ``(deleted_at, id)`` order.
    """
    return health_record_crud.list_deletions(health_fasting_crud.SPEC.sync_type, user_id, after, until, limit, db)
