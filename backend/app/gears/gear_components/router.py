from typing import Annotated, Callable

from fastapi import APIRouter, Depends, HTTPException, status, Security
from sqlalchemy.orm import Session

import session.security as session_security

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
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["gears:read"])
    ],
    token_user_id: Annotated[
        int, Depends(session_security.get_user_id_from_access_token)
    ],
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
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["gears:read"])
    ],
    token_user_id: Annotated[
        int, Depends(session_security.get_user_id_from_access_token)
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    # Return the gear
    return gears_components_crud.get_gear_components_user_by_gear_id(
        token_user_id, gear_id, db
    )


@router.delete("/{gear_component_id}")
async def delete_component_gear(
    gear_component_id: int,
    validate_id: Annotated[
        Callable, Depends(gears_components_dependencies.validate_gear_component_id)
    ],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["gears:write"])
    ],
    token_user_id: Annotated[
        int, Depends(session_security.get_user_id_from_access_token)
    ],
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
