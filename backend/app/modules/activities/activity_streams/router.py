"""Authenticated activity stream endpoints."""

from fastapi import APIRouter, Request, Security

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_streams.dependencies as activity_streams_dependencies
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.activity_streams.service as activity_streams_service
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "/streams",
    response_model=activity_streams_schema.ActivityStreamsPage,
    dependencies=[
        Security(
            auth_dependencies.check_scopes,
            scopes=["activities:read"],
        )
    ],
)
@core_rate_limit.limiter.limit(core_rate_limit.EXPENSIVE_READ)
def list_activity_streams(
    request: Request,
    activity_id: activity_dependencies.ActivityId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: core_pagination.ChildPage,
) -> activity_streams_schema.ActivityStreamsPage:
    """Return one page of the given activity's streams, with the matching total."""
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
    dependencies=[
        Security(
            auth_dependencies.check_scopes,
            scopes=["activities:read"],
        )
    ],
)
@core_rate_limit.limiter.limit(core_rate_limit.EXPENSIVE_READ)
def read_activity_stream(
    request: Request,
    activity_id: activity_dependencies.ActivityId,
    stream_type: activity_streams_dependencies.StreamType,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> activity_streams_schema.ActivityStreamsRead:
    """Get a specific stream type for an activity.

    Not found when the activity has no such stream or is not visible to the
    caller. A single resource that does not exist is a ``404`` rather than
    ``200 null``, and the two cases are indistinguishable so the endpoint cannot
    be used to probe which activities exist.
    """
    return activity_streams_service.get_activity_stream(
        activity_id,
        stream_type,
        token_user_id,
        db,
    )
