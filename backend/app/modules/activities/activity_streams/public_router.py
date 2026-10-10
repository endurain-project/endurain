"""Public activity stream endpoints."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.activities.activity_streams.dependencies as activity_streams_dependencies
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.activity_streams.service as activity_streams_service

router = APIRouter()


@router.get(
    "/streams",
    response_model=activity_streams_schema.ActivityStreamsPage,
)
def read_public_activities_streams_for_activity_all(
    activity_id: int,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.child_page_params)],
) -> activity_streams_schema.ActivityStreamsPage:
    """
    Return one page of a publicly shared activity's streams, with the matching total.

    Args:
        activity_id: The activity identifier.
        db: Database session.
        page: Resolved paging window, capped so one request cannot ask for
            an unbounded number of rows.

    Returns:
        The page envelope. Empty when public sharing is disabled, the activity is
        not public, or it has no visible streams.
    """
    return activity_streams_service.list_public_activity_streams(
        activity_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )


@router.get(
    "/streams/{stream_type}",
    response_model=activity_streams_schema.ActivityStreamsRead,
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
        The activity stream.

    Raises:
        NotFoundError: When the activity has no such stream, is not public, or
            public links are disabled — indistinguishable on purpose, since this
            endpoint is unauthenticated.
    """
    stream = activity_streams_service.get_public_activity_stream(activity_id, stream_type, db)
    if stream is None:
        raise core_exceptions.NotFoundError("Activity stream not found")
    return stream
