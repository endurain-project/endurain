"""Authenticated activity stream endpoints."""

from fastapi import APIRouter, Request, Security

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_streams.dependencies as activity_streams_dependencies
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.activity_streams.service as activity_streams_service
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "/streams",
    response_model=activity_streams_schema.ActivitySamplesRead,
    dependencies=[
        Security(
            auth_dependencies.check_scopes,
            scopes=["activities:read"],
        )
    ],
)
@core_rate_limit.limiter.limit(core_rate_limit.EXPENSIVE_READ)
def read_activity_streams(
    request: Request,
    activity_id: activity_dependencies.ActivityId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    max_points: activity_streams_dependencies.MaxPoints = None,
) -> activity_streams_schema.ActivitySamplesRead:
    """Get an activity's streams: its samples on one timeline, a list per channel.

    Every list is aligned with `offsets_ms`, the sample times in milliseconds from the activity start. A channel the
    activity does not have, or hides from the caller, is `null`. With `max_points` a longer activity is averaged over
    that many equal-time buckets; the heart-rate zones always count every sample. The activity is `404` when it does
    not exist or the caller cannot read it, and an activity with no samples has an empty `offsets_ms` and every channel
    `null`.
    """
    return activity_streams_service.get_activity_streams(activity_id, token_user_id, db, max_points=max_points)
