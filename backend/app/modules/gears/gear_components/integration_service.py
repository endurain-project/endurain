"""The gear components surface other modules may call.

The profile export and import, and the composition root that tells the gear package what
its components cost. The write stages and the caller commits.
"""

from typing import Any

from sqlalchemy.orm import Session

import modules.gears.gear_components.crud as gear_components_crud
import modules.gears.gear_components.schema as gear_components_schema
import modules.gears.gear_components.service as gear_components_service


def get_gear_components_user(user_id: int, db: Session) -> list[gear_components_schema.GearComponentRead]:
    """Return all of a user's gear components.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The user's components (empty list if none).
    """
    return gear_components_crud.get_gear_components_user(user_id, db)


def restore_profile_gear_components(
    records: list[dict[str, Any]], user_id: int, ids: dict[str, dict[int, int]], db: Session
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


def get_gear_components_total_cost(gear_id: int, user_id: int, db: Session) -> float:
    """Return the summed purchase value of a gear's components.

    Args:
        gear_id: Gear to sum costs for.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The total cost, zero when no component has a value.
    """
    return gear_components_crud.get_gear_components_total_cost(gear_id, user_id, db)
