"""The gear components surface other modules may call.

The profile export and import, and the composition root that tells the gear package what
its components cost. The write stages and the caller commits.
"""

import uuid
from collections.abc import Collection
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

import core.sync as core_sync
import modules.gears.gear.schema as gears_schema
import modules.gears.gear_components.crud as gear_components_crud
import modules.gears.gear_components.schema as gear_components_schema
import modules.gears.gear_components.service as gear_components_service
import modules.users.users_profile.contracts as users_profile_contracts


def get_gear_components_user(user_id: uuid.UUID, db: Session) -> list[gear_components_schema.GearComponentRead]:
    """Return all of a user's gear components.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The user's components (empty list if none).
    """
    return gear_components_crud.get_gear_components_user(user_id, db)


def restore_profile_gear_components(
    records: list[dict[str, Any]], user_id: uuid.UUID, ids: users_profile_contracts.ProfileIdMaps, db: Session
) -> int:
    """Stage the gear components of a profile archive; the caller commits.

    Args:
        records: The archived components.
        user_id: The importing user.
        ids: The ids restored so far; the archived-to-stored gear ids are read from ``"gears"``.
        db: Database session.

    Returns:
        How many components were staged.
    """
    return gear_components_service.restore_profile_gear_components(records, user_id, ids, db)


def get_gear_components_total_cost(gear_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> float:
    """Return the summed purchase value of a gear's components.

    Args:
        gear_id: Gear to sum costs for.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The total cost, zero when no component has a value.
    """
    return gear_components_crud.get_gear_components_total_cost(gear_id, user_id, db)


def count_components_outside_gear_type(
    gear_id: uuid.UUID, user_id: uuid.UUID, gear_type: gears_schema.GearType, db: Session
) -> int:
    """Return how many of a gear's components are not valid for a gear type.

    Args:
        gear_id: Gear to count components of.
        user_id: Owner user ID.
        gear_type: The gear type the components would have to fit.
        db: Database session.

    Returns:
        The number of components that do not fit; zero for a gear type that accepts any component.
    """
    return gear_components_service.count_components_outside_gear_type(gear_id, user_id, gear_type, db)


def record_gear_component_deletions(gear_ids: Collection[uuid.UUID], user_id: uuid.UUID, db: Session) -> None:
    """Stage a deletion record for every component of the given gears; the caller commits.

    Call it before deleting the gears, whose delete cascades the components away.

    Args:
        gear_ids: The gears about to be deleted.
        user_id: Owner user ID.
        db: Database session.
    """
    gear_components_crud.record_gear_component_deletions(gear_ids, user_id, db)


def list_changed_gear_components(
    user_id: uuid.UUID, after: core_sync.Position | None, until: datetime, limit: int, db: Session
) -> list[gear_components_schema.GearComponentRead]:
    """Return a page of a user's components changed after a position, oldest change first.

    Args:
        user_id: Owner user ID.
        after: Return components strictly after this ``(updated_at, id)``; None from the first.
        until: Return only components changed before this instant.
        limit: The most components to return.
        db: Database session.

    Returns:
        The components, in ``(updated_at, id)`` order.
    """
    return gear_components_crud.list_changed_gear_components(user_id, after, until, limit, db)


def list_gear_component_deletions(
    user_id: uuid.UUID, after: core_sync.Position | None, until: datetime, limit: int, db: Session
) -> list[core_sync.Deletion]:
    """Return a page of a user's deleted components after a position, oldest deletion first.

    Args:
        user_id: Owner user ID.
        after: Return deletions strictly after this ``(deleted_at, id)``; None from the first.
        until: Return only deletions before this instant.
        limit: The most deletions to return.
        db: Database session.

    Returns:
        The deletions, in ``(deleted_at, id)`` order.
    """
    return gear_components_crud.list_gear_component_deletions(user_id, after, until, limit, db)
