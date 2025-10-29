from typing import Annotated, Callable

from fastapi import APIRouter, Depends, HTTPException, status, Security
from sqlalchemy.orm import Session

import auth.security as auth_security

import gears.gear_components.schema as gears_components_schema
import gears.gear_components.crud as gears_components_crud
import gears.gear_components.dependencies as gears_components_dependencies
import gears.gear.dependencies as gears_dependencies

import core.database as core_database

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=list[gears_components_schema.GearComponents] | None,
)
async def read_gear_components(
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["gears:read"])
    ],
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    # Return the gear_components
    return gears_components_crud.get_gear_components_user(token_user_id, db)


@router.get(
    "/gear_id/{gear_id}",
    response_model=list[gears_components_schema.GearComponents] | None,
)
async def read_gear_components_gear_id(
    gear_id: int,
    validate_gear_id: Annotated[Callable, Depends(gears_dependencies.validate_gear_id)],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["gears:read"])
    ],
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    # Return the gear
    return gears_components_crud.get_gear_components_user_by_gear_id(
        token_user_id, gear_id, db
    )


@router.post(
    "",
    response_model=gears_components_schema.GearComponents,
    status_code=201,
)
async def create_gear_component(
    gear_component: gears_components_schema.GearComponents,
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["gears:write"])
    ],
    verify_gear_type: Annotated[
        Callable, Security(gears_components_dependencies.validate_gear_component_type)
    ],
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Create the gear component and return it
    return gears_components_crud.create_gear_component(
        gear_component, token_user_id, db
    )


@router.put("")
async def edit_gear_component(
    gear_component: gears_components_schema.GearComponents,
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["gears:write"])
    ],
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    if (
        hasattr(gear_component, "retired_date")
        and hasattr(gear_component, "purchase_date")
        and gear_component.retired_date is not None
        and gear_component.purchase_date is not None
        and gear_component.retired_date <= gear_component.purchase_date
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Retired date must be after purchase date",
        )

    # Get the gear component by id
    gear_component_db = gears_components_crud.get_gear_component_by_id(
        gear_component.id, db
    )

    # Check if gear component is None and raise an HTTPException if it is
    if gear_component_db is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gear component ID {gear_component.id} not found",
        )

    if gear_component_db.user_id != token_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Gear component ID {gear_component.id} does not belong to user {token_user_id}",
        )

    # Edit the gear component
    gears_components_crud.edit_gear_component(gear_component, db)

    # Return success message
    return {"detail": f"Gear component ID {gear_component.id} edited successfully"}


@router.delete("/{gear_component_id}")
async def delete_component_gear(
    gear_component_id: int,
    validate_id: Annotated[
        Callable, Depends(gears_components_dependencies.validate_gear_component_id)
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["gears:write"])
    ],
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the gear component by id
    gear_component = gears_components_crud.get_gear_component_by_id(
        gear_component_id, db
    )

    # Check if gear component is None and raise an HTTPException if it is
    if gear_component is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gear component ID {gear_component_id} not found",
        )

    if gear_component.user_id != token_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Gear component ID {gear_component_id} does not belong to user {token_user_id}",
        )

    # Delete the gear component
    gears_components_crud.delete_gear_component(token_user_id, gear_component_id, db)

    # Return success message
    return {"detail": f"Gear component ID {gear_component_id} deleted successfully"}
