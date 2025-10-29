from typing import Annotated, Callable

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

import activities.activity_streams.schema as activity_streams_schema
import activities.activity_streams.crud as activity_streams_crud
import activities.activity_streams.dependencies as activity_streams_dependencies

import activities.activity.dependencies as activities_dependencies

import auth.security as auth_security

import core.database as core_database

# Define the API router
router = APIRouter()


@router.get(
    "/activity_id/{activity_id}/all",
    response_model=list[activity_streams_schema.ActivityStreams] | None,
)
async def read_activities_streams_for_activity_all(
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
    # Get the activity streams from the database and return them
    return activity_streams_crud.get_activity_streams(activity_id, token_user_id, db)


@router.get(
    "/activity_id/{activity_id}/stream_type/{stream_type}",
    response_model=activity_streams_schema.ActivityStreams | None,
)
async def read_activities_streams_for_activity_stream_type(
    activity_id: int,
    validate_activity_id: Annotated[
        Callable, Depends(activities_dependencies.validate_activity_id)
    ],
    stream_type: int,
    validate_activity_stream_type: Annotated[
        Callable, Depends(activity_streams_dependencies.validate_activity_stream_type)
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
    # Get the activity stream from the database and return them
    return activity_streams_crud.get_activity_stream_by_type(
        activity_id, stream_type, token_user_id, db
    )
