from typing import Annotated, Callable

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

import activities.activity_laps.schema as activity_laps_schema
import activities.activity_laps.crud as activity_laps_crud

import activities.activity.dependencies as activities_dependencies

import auth.security as auth_security

import core.database as core_database

# Define the API router
router = APIRouter()


@router.get(
    "/activity_id/{activity_id}/all",
    response_model=list[activity_laps_schema.ActivityLaps] | None,
)
async def read_activities_laps_for_activity_all(
    activity_id: int,
    validate_id: Annotated[
        Callable, Depends(activities_dependencies.validate_activity_id)
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:read"])
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the activity laps from the database and return them
    return activity_laps_crud.get_activity_laps(activity_id, token_user_id, db)
