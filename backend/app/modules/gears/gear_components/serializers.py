"""ORM↔schema transformation for gear components.

``crud`` calls these at its edges so ORM rows never leave the persistence layer.
"""

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
        purchase_value=gear_component.purchase_value,
    )
