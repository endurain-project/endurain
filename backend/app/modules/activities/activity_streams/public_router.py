"""Public activity stream endpoints."""

from fastapi import APIRouter, Request

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_streams.dependencies as activity_streams_dependencies
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.activity_streams.service as activity_streams_service

router = APIRouter()


@router.get(
    "/streams",
    response_model=activity_streams_schema.ActivitySamplesRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.EXPENSIVE_PUBLIC_READ)
def read_public_activity_streams(
    request: Request,
    activity_id: activity_dependencies.ActivityId,
    db: core_dependencies.DbSession,
    max_points: activity_streams_dependencies.MaxPoints = None,
) -> activity_streams_schema.ActivitySamplesRead:
    """Get the streams of a publicly shared activity: its samples on one timeline, a list per channel.

    The shape and `max_points` are those of the authenticated route. A channel the owner hides is `null`. The activity
    is `404` when it is not public, public links are disabled or it does not exist, indistinguishably, since this
    endpoint is unauthenticated.
    """
    return activity_streams_service.get_public_activity_streams(activity_id, db, max_points=max_points)
