"""Public activity stream endpoints."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import core.database as core_database
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_streams.dependencies as activity_streams_dependencies
import modules.activities.activity_streams.schema as activity_streams_schema

router = APIRouter()


@router.get(
    "/streams",
    response_model=(list[activity_streams_schema.ActivityStreamsRead]),
)
def read_public_activities_streams_for_activity_all(
    activity_id: int,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Get all public streams for an activity.

    Args:
        activity_id: The activity identifier.
        validate_id: Activity ID validator dep.
        db: Database session.

    Returns:
        List of activity streams.
    """
    return activity_streams_crud.get_public_activity_streams(activity_id, db)


@router.get(
    "/streams/{stream_type}",
    response_model=(activity_streams_schema.ActivityStreamsRead | None),
)
def read_public_activities_streams_for_activity_stream_type(
    activity_id: int,
    stream_type: int,
    _validate_activity_stream_type: Annotated[
        Callable,
        Depends(activity_streams_dependencies.validate_activity_stream_type),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Get a public stream by type for an activity.

    Args:
        activity_id: The activity identifier.
        stream_type: The stream type code.
        validate_activity_stream_type: Type dep.
        db: Database session.

    Returns:
        The activity stream or None.
    """
    return activity_streams_crud.get_public_activity_stream_by_type(activity_id, stream_type, db)
