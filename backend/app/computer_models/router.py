from typing import Annotated, Callable

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

import auth.security as auth_security

import computer_models.schema as computer_models_schema
import computer_models.crud as computer_models_crud

import core.database as core_database

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=list[computer_models_schema.ComputerModelRead],
)
async def read_computer_models(
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["gears:read"])
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """Get all known watch/computer models"""
    return computer_models_crud.get_all_computer_models(db)


@router.get(
    "/id/{computer_model_id}",
    response_model=computer_models_schema.ComputerModelRead | None,
)
async def read_computer_model_by_id(
    computer_model_id: int,
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["gears:read"])
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """Get a computer model by ID"""
    return computer_models_crud.get_computer_model_by_id(computer_model_id, db)


@router.get(
    "/manufacturer/{manufacturer}",
    response_model=list[computer_models_schema.ComputerModelRead],
)
async def read_computer_models_by_manufacturer(
    manufacturer: str,
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["gears:read"])
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """Get all computer models for a specific manufacturer"""
    return computer_models_crud.get_computer_models_by_manufacturer(manufacturer, db)
