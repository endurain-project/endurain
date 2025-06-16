from fastapi import HTTPException, status

import core.dependencies as core_dependencies

import gears.gear_components.schema as gear_components_schema


def validate_gear_component_id(gear_component_id: int):
    """
    Validates that the provided gear component ID is greater than zero.

    Args:
        gear_component_id (int): The ID of the gear component to validate.

    Raises:
        ValueError: If the gear_component_id is less than or equal to zero.

    Returns:
        None
    """
    # Check if id higher than 0
    core_dependencies.validate_id(
        id=gear_component_id, min=0, message="Invalid gear component ID"
    )


def validate_gear_component_type(gear_component_type: str):
    """
    Validates that the provided gear component type is within the allowed types.

    Args:
        gear_component_type (str): The type of the gear component to validate.

    Raises:
        HTTPException: If the gear component type is not valid, raises an HTTP 422 error.
    """
    if (
        gear_component_type not in gear_components_schema.GEAR_COMPONENT_TYPES
        and gear_component_type is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid gear component type field",
        )
