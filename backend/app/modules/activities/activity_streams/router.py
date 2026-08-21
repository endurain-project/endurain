"""Authenticated activity stream endpoints."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.activities.activity_streams.dependencies as activity_streams_dependencies
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.activity_streams.service as activity_streams_service
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "/streams",
    response_model=activity_streams_schema.ActivityStreamsPage,
)
def read_activities_streams_for_activity_all(
    activity_id: int,
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
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.child_page_params)],
) -> activity_streams_schema.ActivityStreamsPage:
    """
    Return one page of the given activity's streams, with the matching total.

    Args:
        activity_id: The activity identifier.
        _check_scopes: Scope authorization dep.
        token_user_id: Authenticated user ID.
        db: Database session.
        page: Resolved paging window, capped so one request cannot ask for
            an unbounded number of rows.

    Returns:
        The page envelope. Empty when the activity is hidden from the caller or
        has no visible streams.
    """
    return activity_streams_service.list_activity_streams(
        activity_id,
        token_user_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )


@router.get(
    "/streams/{stream_type}",
    response_model=activity_streams_schema.ActivityStreamsRead,
)
def read_activities_streams_for_activity_stream_type(
    activity_id: int,
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
        stream_type: The stream type code.
        validate_activity_stream_type: Type dep.
        _check_scopes: Scope authorization dep.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        The activity stream.

    Raises:
        NotFoundError: When the activity has no such stream, or is not visible
            to the caller. A single resource that does not exist is a 404; it
            used to answer ``200 null``, which is neither a resource nor an
            error. The two cases are deliberately indistinguishable so the
            endpoint cannot be used to probe which activities exist.
    """
    stream = activity_streams_service.get_activity_stream(
        activity_id,
        stream_type,
        token_user_id,
        db,
    )
    if stream is None:
        raise core_exceptions.NotFoundError("Activity stream not found")
    return stream
