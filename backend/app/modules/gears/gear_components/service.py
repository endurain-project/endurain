"""Application logic for gear components.

Owns the transaction for every write the router makes. What other modules may consume
lives in :mod:`modules.gears.gear_components.integration_service`.
"""

from datetime import date

from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

import core.exceptions as core_exceptions
import core.logger as core_logger
import core.pagination as core_pagination
import modules.gears.contracts as gears_contracts
import modules.gears.contributor_registry as gears_contributor_registry
import modules.gears.gear.integration_service as gears_integration
import modules.gears.gear.schema as gears_schema
import modules.gears.gear_components.constants as gear_components_constants
import modules.gears.gear_components.crud as gear_components_crud
import modules.gears.gear_components.schema as gear_components_schema

logger = core_logger.get_logger(__name__)


def _require_retired_after_purchase(purchase_date: date | None, retired_date: date | None) -> None:
    """Reject a retired date that is not after the purchase date.

    Args:
        purchase_date: The purchase date, if given.
        retired_date: The retired date, if given.

    Raises:
        InvalidInputError: If both are given and the retired date is not later.
    """
    if retired_date is not None and purchase_date is not None and retired_date <= purchase_date:
        raise core_exceptions.InvalidInputError("Retired date must be after purchase date")


def _require_type_for_gear(gear: gears_schema.GearRead, component_type: str) -> None:
    """Reject a component type that does not fit the gear's type.

    Args:
        gear: The gear the component belongs to.
        component_type: The component type to check.

    Raises:
        InvalidInputError: If the type is not valid for the gear type.
    """
    valid_types = gear_components_constants.COMPONENT_TYPES_BY_GEAR_TYPE.get(gear.gear_type)
    if valid_types is not None and component_type not in valid_types:
        raise core_exceptions.InvalidInputError(f"Invalid gear component type for {gear.gear_type.name.lower()}")


def read_component_types() -> gear_components_schema.GearComponentTypesRead:
    """Return the valid component types, grouped by gear type.

    Returns:
        The component type lists.
    """
    return gear_components_schema.GearComponentTypesRead(
        bike=gear_components_constants.BIKE_COMPONENT_TYPES,
        shoes=gear_components_constants.SHOES_COMPONENT_TYPES,
        racquet=gear_components_constants.RACQUET_COMPONENT_TYPES,
        windsurf=gear_components_constants.WINDSURF_COMPONENT_TYPES,
    )


def list_gear_components(user_id: int, db: Session) -> list[gear_components_schema.GearComponentRead]:
    """Return up to ``MAX_NUM_RECORDS`` of a user's gear components.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The user's components (empty list if none).
    """
    return gear_components_crud.get_gear_components_user(user_id, db, limit=core_pagination.MAX_NUM_RECORDS)


def list_components_for_gear(
    gear_id: int,
    user_id: int,
    db: Session,
    *,
    active: bool | None = None,
) -> list[gear_components_schema.GearComponentRead]:
    """Return a gear's components with the distance and time each has accumulated.

    Each component accumulates the activities recorded against the gear between its
    purchase date and retired date.

    Args:
        gear_id: Gear ID to filter by.
        user_id: Owner user ID.
        db: Database session.
        active: Optional active-status filter.

    Returns:
        The matching components (empty list if none).
    """
    components = gear_components_crud.get_gear_components_user_by_gear_id(user_id, gear_id, db, active=active)
    if not components:
        return components

    windows = gear_components_crud.list_usage_windows(gear_id, user_id, db)
    totals = gears_contributor_registry.readers().usage_by_window(gear_id, user_id, windows, db)
    no_usage = gears_contracts.UsageTotals()
    return [
        component.model_copy(
            update={
                "current_distance": totals.get(component.id, no_usage).distance,
                "current_time": totals.get(component.id, no_usage).time,
            }
        )
        for component in components
    ]


def create_gear_component(
    gear_component: gear_components_schema.GearComponentCreate,
    user_id: int,
    db: Session,
) -> gear_components_schema.GearComponentRead:
    """Create a component on one of the user's gears.

    Args:
        gear_component: Component payload to create.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The created component.

    Raises:
        NotFoundError: If the user has no such gear.
        InvalidInputError: If the component type does not fit the gear type, or the retired
            date is not after the purchase date.
    """
    _require_retired_after_purchase(gear_component.purchase_date, gear_component.retired_date)
    gear = gears_integration.get_gear_user_by_id(user_id, gear_component.gear_id, db)
    if gear is None:
        raise core_exceptions.NotFoundError("Gear not found")

    _require_type_for_gear(gear, gear_component.type)

    created = gear_components_crud.create_gear_component(gear_component, user_id, db)
    db.commit()
    logger.info("Created a gear component", extra=core_logger.context(user_id=user_id, gear_component_id=created.id))
    return created


def edit_gear_component(
    gear_component_id: int,
    gear_component: gear_components_schema.GearComponentUpdate,
    user_id: int,
    db: Session,
    *,
    if_match: str | None = None,
) -> gear_components_schema.GearComponentRead:
    """Update one of the user's components.

    Args:
        gear_component_id: Component ID to update.
        gear_component: Component payload with the fields to change.
        user_id: Owner user ID.
        db: Database session.
        if_match: The ``If-Match`` precondition, or None.

    Returns:
        The updated component.

    Raises:
        InvalidInputError: If the type does not fit the gear type, or the resulting retired
            date is not after the resulting purchase date.
        NotFoundError: If the user has no such component.
        PreconditionFailedError: If the component changed since the client read it.
    """
    current = gear_components_crud.get_gear_component_user_by_id(user_id, gear_component_id, db)
    if current is None:
        raise core_exceptions.NotFoundError("Gear component not found")

    changed = gear_component.model_fields_set
    _require_retired_after_purchase(
        gear_component.purchase_date if "purchase_date" in changed else current.purchase_date,
        gear_component.retired_date if "retired_date" in changed else current.retired_date,
    )
    if "type" in changed and gear_component.type != current.type:
        gear = gears_integration.get_gear_user_by_id(user_id, current.gear_id, db)
        if gear is None:
            raise core_exceptions.NotFoundError("Gear not found")
        _require_type_for_gear(gear, gear_component.type)

    try:
        updated = gear_components_crud.edit_gear_component(
            gear_component_id, gear_component, user_id, db, if_match=if_match
        )
        db.commit()
    except StaleDataError as err:
        db.rollback()
        if gear_components_crud.get_gear_component_user_by_id(user_id, gear_component_id, db) is None:
            raise core_exceptions.NotFoundError("Gear component not found") from err
        raise core_exceptions.PreconditionFailedError(
            "The gear component was modified by someone else; re-read it and retry"
        ) from err
    logger.info("Edited a gear component", extra=core_logger.context(user_id=user_id, gear_component_id=updated.id))
    return updated


def delete_gear_component(user_id: int, gear_component_id: int, db: Session) -> None:
    """Delete one of the user's components.

    Args:
        user_id: Owner user ID.
        gear_component_id: Component ID to delete.
        db: Database session.

    Raises:
        NotFoundError: If the user has no such component.
    """
    gear_components_crud.delete_gear_component(user_id, gear_component_id, db)
    db.commit()
    logger.info(
        "Deleted a gear component", extra=core_logger.context(user_id=user_id, gear_component_id=gear_component_id)
    )
