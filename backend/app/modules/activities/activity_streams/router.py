"""Authenticated activity stream endpoints."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

import core.database as core_database
import modules.activities.activity.dependencies as activities_dependencies
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_streams.dependencies as activity_streams_dependencies
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "/activity_id/{activity_id}/all",
    response_model=(list[activity_streams_schema.ActivityStreamsRead]),
)
def read_activities_streams_for_activity_all(
    activity_id: int,
    _validate_id: Annotated[
        Callable,
        Depends(activities_dependencies.validate_activity_id),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_scopes,
            scopes=["activities:read"],
        ),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Get all streams for an activity.

    Args:
        activity_id: The activity identifier.
        validate_id: Activity ID validator dep.
        _check_scopes: Scope authorization dep.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        List of activity streams or None.
    """
    return activity_streams_crud.get_activity_streams(activity_id, token_user_id, db)


@router.get(
    "/activity_id/{activity_id}/stream_type/{stream_type}",
    response_model=(activity_streams_schema.ActivityStreamsRead | None),
)
def read_activities_streams_for_activity_stream_type(
    activity_id: int,
    _validate_activity_id: Annotated[
        Callable,
        Depends(activities_dependencies.validate_activity_id),
    ],
    stream_type: int,
    _validate_activity_stream_type: Annotated[
        Callable,
        Depends(activity_streams_dependencies.validate_activity_stream_type),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_scopes,
            scopes=["activities:read"],
        ),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Get a specific stream type for an activity.

    Args:
        activity_id: The activity identifier.
        validate_activity_id: Activity ID dep.
        stream_type: The stream type code.
        validate_activity_stream_type: Type dep.
        _check_scopes: Scope authorization dep.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        The activity stream or None.
    """
    return activity_streams_crud.get_activity_stream_by_type(
        activity_id,
        stream_type,
        token_user_id,
        db,
    )
