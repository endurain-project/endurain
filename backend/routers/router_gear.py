import logging

from typing import Annotated, Callable

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from schemas import schema_gear
from crud import crud_gear
from dependencies import (
    dependencies_database,
    dependencies_session,
    dependencies_global,
    dependencies_gear,
)

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


@router.get(
    "/gear/id/{gear_id}",
    response_model=schema_gear.Gear | None,
    tags=["gear"],
)
async def read_gear_id(
    gear_id: int,
    validate_gear_id: Annotated[Callable, Depends(dependencies_gear.validate_gear_id)],
    user_id: Annotated[
        int, Depends(dependencies_session.validate_access_token_and_get_authenticated_user_id)
    ],
    db: Annotated[Session, Depends(dependencies_database.get_db)],
):
    # Return the gear
    return crud_gear.get_gear_user_by_id(user_id, gear_id, db)


@router.get(
    "/gear/page_number/{page_number}/num_records/{num_records}",
    response_model=list[schema_gear.Gear] | None,
    tags=["gear"],
)
async def read_gear_user_pagination(
    page_number: int,
    num_records: int,
    validate_pagination_values: Annotated[
        Callable, Depends(dependencies_global.validate_pagination_values)
    ],
    user_id: Annotated[
        int, Depends(dependencies_session.validate_access_token_and_get_authenticated_user_id)
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Return the gear
    return crud_gear.get_gear_users_with_pagination(
        user_id, db, page_number, num_records
    )


@router.get(
    "/gear/number",
    response_model=int,
    tags=["gear"],
)
async def read_gear_user_number(
    user_id: Annotated[
        int, Depends(dependencies_session.validate_access_token_and_get_authenticated_user_id)
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the gear
    gear = crud_gear.get_gear_user(user_id, db)

    # Check if gear is None and return 0 if it is
    if gear is None:
        return 0

    # Return the number of gears
    return len(gear)


@router.get(
    "/gear/nickname/{nickname}",
    response_model=list[schema_gear.Gear] | None,
    tags=["gear"],
)
async def read_gear_user_by_nickname(
    nickname: str,
    user_id: Annotated[
        int, Depends(dependencies_session.validate_access_token_and_get_authenticated_user_id)
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Return the gear
    return crud_gear.get_gear_user_by_nickname(user_id, nickname, db)


@router.get(
    "/gear/type/{gear_type}",
    response_model=list[schema_gear.Gear] | None,
    tags=["gear"],
)
async def read_gear_user_by_type(
    gear_type: int,
    validate_type: Annotated[Callable, Depends(dependencies_gear.validate_gear_type)],
    user_id: Annotated[
        int, Depends(dependencies_session.validate_access_token_and_get_authenticated_user_id)
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Return the gear
    return crud_gear.get_gear_by_type_and_user(gear_type, user_id, db)


@router.post(
    "/gear/create",
    status_code=201,
    tags=["gear"],
)
async def create_gear(
    gear: schema_gear.Gear,
    user_id: Annotated[
        int, Depends(dependencies_session.validate_access_token_and_get_authenticated_user_id)
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Create the gear
    gear_created = crud_gear.create_gear(gear, user_id, db)

    # Return the ID of the gear created
    return gear_created.id


@router.put("/gear/{gear_id}/edit", tags=["gear"])
async def edit_gear(
    gear_id: int,
    validate_id: Annotated[Callable, Depends(dependencies_gear.validate_gear_id)],
    gear: schema_gear.Gear,
    token_user_id: Annotated[
        int, Depends(dependencies_session.validate_access_token_and_get_authenticated_user_id)
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the gear by id
    gear_db = crud_gear.get_gear_user_by_id(token_user_id, gear_id, db)

    # Check if gear is None and raise an HTTPException if it is
    if gear_db is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gear ID {gear_id} for user {token_user_id} not found",
        )

    # Edit the gear
    crud_gear.edit_gear(gear_id, gear, db)

    # Return success message
    return {"detail": f"Gear ID {gear_id} edited successfully"}


@router.delete("/gear/{gear_id}/delete", tags=["gear"])
async def delete_user(
    gear_id: int,
    validate_id: Annotated[Callable, Depends(dependencies_gear.validate_gear_id)],
    token_user_id: Annotated[
        int, Depends(dependencies_session.validate_access_token_and_get_authenticated_user_id)
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the gear by id
    gear = crud_gear.get_gear_user_by_id(token_user_id, gear_id, db)

    # Check if gear is None and raise an HTTPException if it is
    if gear is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gear ID {gear_id} for user {token_user_id} not found",
        )

    # Delete the gear
    crud_gear.delete_gear(gear_id, db)

    # Return success message
    return {"detail": f"Gear ID {gear_id} deleted successfully"}
