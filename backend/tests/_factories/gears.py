"""Gears and gear components as the application stores them, for tests on the real database."""

import uuid

from sqlalchemy.orm import Session

import modules.gears.gear.crud as gears_crud
import modules.gears.gear.schema as gears_schema
import modules.gears.gear_components.crud as gear_components_crud
import modules.gears.gear_components.schema as gear_components_schema


def make_gear(db: Session, user_id: uuid.UUID, **overrides: object) -> gears_schema.GearRead:
    """Stage a gear through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        user_id: The gear's owner.
        **overrides: Field values of :class:`~modules.gears.gear.schema.GearCreateRequest`, which replace the
            defaults of an active road bike.

    Returns:
        The staged gear.
    """
    values: dict[str, object] = {"nickname": "Road bike", "gear_type": "bike"}
    values.update(overrides)
    return gears_crud.create_gear(gears_schema.GearCreateRequest.model_validate(values), user_id, db)


def make_gear_component(
    db: Session, user_id: uuid.UUID, gear_id: uuid.UUID, **overrides: object
) -> gear_components_schema.GearComponentRead:
    """Stage a gear component through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        user_id: The component's owner.
        gear_id: The gear the component belongs to.
        **overrides: Field values of :class:`~modules.gears.gear_components.schema.GearComponentCreate`, which
            replace the defaults of a chain.

    Returns:
        The staged component.
    """
    values: dict[str, object] = {"type": "chain", "brand": "Shimano", "model": "CN-HG71", "gear_id": gear_id}
    values.update(overrides)
    return gear_components_crud.create_gear_component(
        gear_components_schema.GearComponentCreate.model_validate(values), user_id, db
    )


def gear_payload(nickname: str = "Road Bike", **overrides: object) -> gears_schema.GearCreate:
    """Build the payload the provider syncs and the profile import hand to the module, with provider ids allowed.

    Args:
        nickname: The gear's nickname.
        **overrides: Field values of :class:`~modules.gears.gear.schema.GearCreate`, which replace the defaults of a
            bike.

    Returns:
        The payload, not yet stored.
    """
    values: dict[str, object] = {"nickname": nickname, "gear_type": gears_schema.GearType.BIKE}
    values.update(overrides)
    return gears_schema.GearCreate.model_validate(values)


def component_payload(gear_id: uuid.UUID, **overrides: object) -> gear_components_schema.GearComponentCreate:
    """Build the payload for a component on a gear.

    Args:
        gear_id: The gear the component belongs to.
        **overrides: Field values of :class:`~modules.gears.gear_components.schema.GearComponentCreate`, which
            replace the defaults of a chain.

    Returns:
        The payload, not yet stored.
    """
    values: dict[str, object] = {"gear_id": gear_id, "type": "chain", "brand": "Shimano", "model": "XT"}
    values.update(overrides)
    return gear_components_schema.GearComponentCreate.model_validate(values)
