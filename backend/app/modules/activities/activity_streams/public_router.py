"""Public activity stream endpoints."""

from fastapi import APIRouter, Request

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_streams.dependencies as activity_streams_dependencies
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.activity_streams.service as activity_streams_service

router = APIRouter()


@router.get(
    "/streams",
    response_model=activity_streams_schema.ActivityStreamsPage,
)
@core_rate_limit.limiter.limit(core_rate_limit.EXPENSIVE_PUBLIC_READ)
def list_public_activity_streams(
    request: Request,
    activity_id: activity_dependencies.ActivityId,
    db: core_dependencies.DbSession,
    page: core_pagination.ChildPage,
) -> activity_streams_schema.ActivityStreamsPage:
    """Return one page of a publicly shared activity's streams, with the matching total."""
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
@core_rate_limit.limiter.limit(core_rate_limit.EXPENSIVE_PUBLIC_READ)
def read_public_activity_stream(
    request: Request,
    activity_id: activity_dependencies.ActivityId,
    stream_type: activity_streams_dependencies.StreamType,
    db: core_dependencies.DbSession,
) -> activity_streams_schema.ActivityStreamsRead:
    """Get a public stream by type for an activity.

    Not found when the activity has no such stream, is not public, or public links
    are disabled. The cases are indistinguishable on purpose, since this endpoint
    is unauthenticated.
    """
    return activity_streams_service.get_public_activity_stream(activity_id, stream_type, db)
