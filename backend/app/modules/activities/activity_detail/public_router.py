"""Public route for the combined activity detail of a shared activity."""

from fastapi import APIRouter, Request

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_detail.schema as activity_detail_schema
import modules.activities.activity_detail.service as activity_detail_service

router = APIRouter()


@router.get(
    "/detail",
    response_model=activity_detail_schema.ActivityDetailRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.PUBLIC_READ)
def read_public_activity_detail(
    request: Request,
    activity_id: activity_dependencies.ActivityId,
    db: core_dependencies.DbSession,
) -> activity_detail_schema.ActivityDetailRead:
    """Return a shared activity with its laps, sets and workout steps in one read.

    Answers 404 when the activity does not exist *or* is not public, so it cannot be used to
    enumerate which ids exist. A collection the owner hides is an empty page.
    """
    return activity_detail_service.get_public_activity_detail(activity_id, db)
