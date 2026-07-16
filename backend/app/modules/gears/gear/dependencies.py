"""Gear dependency validators."""

from fastapi import HTTPException, status

import core.dependencies as core_dependencies
import modules.gears.gear.schema as gears_schema


def validate_gear_id(gear_id: int) -> None:
    """
    Validate that gear_id is greater than zero.

    Args:
        gear_id: The ID of the gear to validate.

    Raises:
        HTTPException: If gear_id is invalid.
    """
    core_dependencies.validate_id(
        identifier=gear_id,
        min_value=0,
        message="Invalid gear ID",
    )


def validate_gear_type(gear_type: int) -> None:
    """
    Validate that gear_type maps to a known GearType.

    Args:
        gear_type: The type of gear to validate.

    Raises:
        HTTPException: If gear_type is invalid.
    """
    try:
        gears_schema.GearType(gear_type)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid gear type",
        ) from err
