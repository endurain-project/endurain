"""The operations other modules may call on health fasting records.

The writes stage; the caller owns the unit of work and commits.
"""

from sqlalchemy.orm import Session

import modules.health.health_fasting.crud as health_fasting_crud
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.health_fasting.service as health_fasting_service
import modules.users.users_profile.contracts as users_profile_contracts


def get_active_fasting(user_id: int, db: Session) -> health_fasting_schema.HealthFastingRead | None:
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
