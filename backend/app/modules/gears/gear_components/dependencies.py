"""Gear components dependency validators."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import modules.auth.dependencies as auth_dependencies
import modules.gears.gear.crud as gears_crud
import modules.gears.gear_components.schema as gc_schema


def validate_gear_component_id(
    gear_component_id: int,
) -> None:
    """
    Validate gear component ID is above zero.

    Args:
        gear_component_id: Component ID.

    Raises:
        HTTPException: If ID is invalid.
    """
    core_dependencies.validate_id(
        identifier=gear_component_id,
        min_value=0,
        message="Invalid gear component ID",
    )


def validate_gear_component_type(
    gear_component: (gc_schema.GearComponentCreate),
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> None:
    """
    Validate component type for the gear.

    Args:
        gear_component: Create schema data.
        token_user_id: Authenticated user ID.
        db: Database session.

    Raises:
        HTTPException: If gear not found (404).
        HTTPException: If type is invalid (422).
    """
    gear = gears_crud.get_gear_user_by_id(
        token_user_id,
        gear_component.gear_id,
        db,
    )

    if gear is None:
        raise HTTPException(
            status_code=(status.HTTP_404_NOT_FOUND),
            detail="Gear not found",
        )

    gear_type_to_component_types = {
        1: gc_schema.BIKE_COMPONENT_TYPES,
        2: gc_schema.SHOES_COMPONENT_TYPES,
        4: gc_schema.RACQUET_COMPONENT_TYPES,
        7: gc_schema.WINDSURF_COMPONENT_TYPES,
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
                status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
                detail=(f"Invalid gear component type for {gear_type_names[gear.gear_type]}"),
            )
