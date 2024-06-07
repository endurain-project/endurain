import logging

from typing import Annotated, Callable

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from schemas import schema_activity_streams
from crud import crud_activity_streams
from dependencies import (
    dependencies_database,
    dependencies_security,
    dependencies_activities,
    dependencies_activity_streams,
)

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


@router.get(
    "/activities/streams/activity_id/{activity_id}/all",
    response_model=list[schema_activity_streams.ActivityStreams] | None,
    tags=["activity_streams"],
)
async def read_activities_streams_for_activity_all(
    activity_id: int,
    validate_id: Annotated[
        Callable, Depends(dependencies_activities.validate_activity_id)
    ],
    validate_token_validate_admin_access: Annotated[
        Callable, Depends(dependencies_security.validate_token_expiration)
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the activity streams from the database and return them
    return crud_activity_streams.get_activity_streams(activity_id, db)


@router.get(
    "/activities/streams/activity_id/{activity_id}/stream_type/{stream_type}",
    response_model=schema_activity_streams.ActivityStreams | None,
    tags=["activity_streams"],
)
async def read_activities_streams_for_activity_stream_type(
    activity_id: int,
    validate_activity_id: Annotated[
        Callable, Depends(dependencies_activities.validate_activity_id)
    ],
    stream_type: int,
    validate_activity_stream_type: Annotated[
        Callable, Depends(dependencies_activity_streams.validate_activity_stream_type)
    ],
    validate_token: Annotated[
        Callable, Depends(dependencies_security.validate_token_expiration)
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the activity stream from the database and return them
    return crud_activity_streams.get_activity_stream_by_type(
        activity_id, stream_type, db
    )
