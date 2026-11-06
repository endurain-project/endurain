"""ORM↔schema transformation for gear components.

``crud`` calls these at its edges so ORM rows never leave the persistence layer.
"""

from decimal import Decimal

import modules.gears.gear_components.models as gear_components_models
import modules.gears.gear_components.schema as gear_components_schema


def to_read_schema(
    gear_component: gear_components_models.GearComponents,
) -> gear_components_schema.GearComponentRead:
    """Convert an ORM row to its Read schema.

    Args:
        gear_component: The ORM row to convert.

    Returns:
        The component as a schema.
    """
    return gear_components_schema.GearComponentRead.model_validate(gear_component)


def to_orm(
    gear_component: gear_components_schema.GearComponentCreate, user_id: int
) -> gear_components_models.GearComponents:
    """Build an unsaved ORM row from a create payload.

    A component starts active unless it is created already retired.

    Args:
        gear_component: The component to create.
        user_id: The owning user.

    Returns:
        An unsaved GearComponents instance.
    """
    return gear_components_models.GearComponents(
        user_id=user_id,
        gear_id=gear_component.gear_id,
        type=gear_component.type,
        brand=gear_component.brand,
        model=gear_component.model,
        purchase_date=gear_component.purchase_date,
        retired_date=gear_component.retired_date,
        active=gear_component.retired_date is None and gear_component.active is not False,
        expected_kms=gear_component.expected_kms,
        purchase_value=Decimal(gear_component.purchase_value) if gear_component.purchase_value is not None else None,
    )


def to_update_values(gear_component: gear_components_schema.GearComponentUpdate) -> dict[str, object]:
    """Return the columns an update payload changes.

    Args:
        gear_component: The update payload.

    Returns:
        The fields the client sent, with the purchase price as a ``Decimal``.
    """
    values: dict[str, object] = dict(gear_component.model_dump(exclude_unset=True))
    purchase_value = values.get("purchase_value")
    if isinstance(purchase_value, str):
        values["purchase_value"] = Decimal(purchase_value)
    return values
