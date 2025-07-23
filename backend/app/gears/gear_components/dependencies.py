from typing import Annotated, Callable

from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, status

import core.database as core_database

import core.dependencies as core_dependencies

import gears.gear.crud as gears_crud

import gears.gear_components.schema as gears_components_schema


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


def validate_gear_component_type(
    gear_component: gears_components_schema.GearComponents,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Validates that the gear component type is appropriate for the specified gear.

    Args:
        gear_component (gears_components_schema.GearComponents): The gear component to validate, containing user_id, gear_id, and type.
        db (Session): Database session dependency.

    Raises:
        HTTPException: If the gear is not found for the user and gear_id.
        HTTPException: If the gear component type is not valid for the gear's type.
    """
    gear = gears_crud.get_gear_user_by_id(
        gear_component.user_id, gear_component.gear_id, db
    )

    if gear is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gear not found",
        )

    gear_type_to_component_types = {
        1: gears_components_schema.BIKE_COMPONENT_TYPES,
        2: gears_components_schema.SHOES_COMPONENT_TYPES,
        4: gears_components_schema.RACQUET_COMPONENT_TYPES,
        7: gears_components_schema.WINDSURF_COMPONENT_TYPES,
    }

    if gear.gear_type in gear_type_to_component_types:
        valid_types = gear_type_to_component_types[gear.gear_type]
        if gear_component.type not in valid_types:
            gear_type_names = {
                1: "bike",
                2: "shoes",
                4: "racquet",
                7: "windsurf",
            }
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid gear component type for {gear_type_names[gear.gear_type]}",
            )
