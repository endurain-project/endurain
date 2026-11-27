"""Application logic for per-user health targets.

The module's own application layer; what other modules may consume lives in
:mod:`modules.health.health_targets.integration_service`.
"""

import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

import core.etag as core_etag
import core.logger as core_logger
import modules.health.health_targets.crud as health_targets_crud
import modules.health.health_targets.schema as health_targets_schema
import modules.users.users_profile.contracts as users_profile_contracts

logger = core_logger.get_logger(__name__)


def get_health_targets(user_id: uuid.UUID, db: Session) -> health_targets_schema.HealthTargetsRead | None:
    """Return a user's health targets.

    Args:
        user_id: The targets' owner.
        db: Database session.

    Returns:
        The user's targets, or ``None`` when they have none.
    """
    return health_targets_crud.get_health_targets_by_user_id(user_id, db)


def update_health_targets(
    health_targets: health_targets_schema.HealthTargetsUpdate,
    user_id: uuid.UUID,
    db: Session,
    *,
    if_match: str,
) -> health_targets_schema.HealthTargetsRead:
    """Update a user's health targets and commit.

    Args:
        health_targets: The fields to update.
        user_id: The targets' owner.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated targets.

    Raises:
        NotFoundError: If the user has no targets.
        PreconditionFailedError: If the targets changed since the client read them.
    """
    with core_etag.refuse_stale_write(
        db,
        "health targets",
        lambda: health_targets_crud.health_targets_exists(user_id, db),
        "Health targets not found",
    ):
        updated = health_targets_crud.edit_health_targets(health_targets, user_id, db, if_match=if_match)
        db.commit()
    logger.info("Updated health targets", extra=core_logger.context(user_id=user_id))
    return updated


def restore_profile_records(
    records: list[dict[str, Any]], user_id: uuid.UUID, ids: users_profile_contracts.ProfileIdMaps, db: Session
) -> int:
    """Stage the health targets of a profile archive for a user.

    The user's targets exist from the day the account was created, so the archived ones edit them.

    Args:
        records: The archived rows.
        user_id: The importing user.
        ids: The ids restored by earlier sections; the targets read none.
        db: Database session.

    Returns:
        The number of targets staged.

    Raises:
        NotFoundError: If the user has no targets.
    """
    staged = 0
    for archived in records:
        target_data = dict(archived)
        # Convert string numeric values to floats/ints
        if isinstance(target_data.get("weight_kg"), str):
            try:
                target_data["weight_kg"] = float(target_data["weight_kg"])
            except (ValueError, TypeError):
                target_data["weight_kg"] = None

        int_fields = ["steps", "sleep_seconds"]
        for field in int_fields:
            if isinstance(target_data.get(field), str):
                try:
                    target_data[field] = int(target_data[field])
                except (ValueError, TypeError):
                    target_data[field] = None

        # Only the editable fields: the export also carries the row's id, owner and version.
        editable = health_targets_schema.HealthTargetsUpdate.model_fields
        try:
            target = health_targets_schema.HealthTargetsUpdate(
                **{key: value for key, value in target_data.items() if key in editable}
            )
        except ValidationError:
            logger.warning("Skipped invalid health targets")
            continue
        # A system writer (the profile importer), so it names no version.
        health_targets_crud.edit_health_targets(target, user_id, db, if_match="*")
        staged += 1
    logger.debug("Imported health targets", extra=core_logger.context(count=staged))
    return staged
