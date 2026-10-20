"""The gear components surface other modules may call.

The profile export and import, and the composition root that tells the gear package what
its components cost. The write stages and the caller commits.
"""

from sqlalchemy.orm import Session

import modules.gears.gear_components.crud as gear_components_crud
import modules.gears.gear_components.schema as gear_components_schema


def get_gear_components_user(user_id: int, db: Session) -> list[gear_components_schema.GearComponentRead]:
    """Return all of a user's gear components.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The user's components (empty list if none).
    """
    return gear_components_crud.get_gear_components_user(user_id, db)


def create_gear_component(
    gear_component: gear_components_schema.GearComponentCreate,
    user_id: int,
    db: Session,
) -> gear_components_schema.GearComponentRead:
    """Stage a gear component restored from a profile archive; the caller commits.

    The caller has already mapped the component onto one of the user's gears.

    Args:
        gear_component: Component payload to create.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The staged component with its generated ID.
    """
    return gear_components_crud.create_gear_component(gear_component, user_id, db)


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
