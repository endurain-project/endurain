from typing import Annotated, Callable

from fastapi import (
    APIRouter,
    Depends,
    Security,
)
from sqlalchemy.orm import Session

import activities.activity.schema as activities_schema
import activities.activity.crud as activities_crud
import activities.activity.dependencies as activities_dependencies

import core.database as core_database

# Define the API router
router = APIRouter()

@router.get(
    "/{activity_id}",
    response_model=activities_schema.Activity | None,
)
async def read_public_activities_activity_from_id(
    activity_id: int,
    validate_activity_id: Annotated[
        Callable, Depends(activities_dependencies.validate_activity_id)
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the activity from the database and return it
    return activities_crud.get_activity_by_id_if_is_public(
        activity_id, db
    )