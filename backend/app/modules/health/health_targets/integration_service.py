"""The operations other modules may call on health targets.

The writes stage; the caller owns the unit of work and commits.
"""

from sqlalchemy.orm import Session

import modules.health.health_targets.crud as health_targets_crud
import modules.health.health_targets.schema as health_targets_schema
import modules.health.health_targets.service as health_targets_service
import modules.users.users_profile.contracts as users_profile_contracts


def get_health_targets(user_id: int, db: Session) -> health_targets_schema.HealthTargetsRead | None:
    """Return a user's health targets, or ``None`` when they have none.

    Args:
        user_id: The targets' owner.
        db: Database session.

    Returns:
        The user's targets, or ``None``.
    """
    return health_targets_crud.get_health_targets_by_user_id(user_id, db)


def create_health_targets(user_id: int, db: Session) -> health_targets_schema.HealthTargetsRead:
    """Stage empty health targets for a new user.

    Args:
        user_id: The targets' owner.
        db: Database session.

    Returns:
        The staged targets.

    Raises:
        ConflictError: If the user already has targets.
    """
    return health_targets_crud.create_health_targets(user_id, db)


def _export_health_targets(user_id: int, db: Session) -> list[health_targets_schema.HealthTargetsRead]:
    """Return a user's health targets as the one-record list an archive carries.

    Args:
        user_id: The targets' owner.
        db: Database session.

    Returns:
        The targets, or an empty list when the user has none.
    """
    targets = health_targets_crud.get_health_targets_by_user_id(user_id, db)
    return [targets] if targets else []


def profile_section() -> users_profile_contracts.ProfileRecordsSection:
    """Return the health targets' section of a profile export and import.

    Returns:
        The section, which exports a user's targets and edits the ones the account has with the archived ones.
    """
    return users_profile_contracts.ProfileRecordsSection(
        key="health_targets", export=_export_health_targets, restore=health_targets_service.restore_profile_records
    )
