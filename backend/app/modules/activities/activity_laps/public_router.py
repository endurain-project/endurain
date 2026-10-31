"""Public (unauthenticated) routes for activity laps."""

from fastapi import APIRouter, Request

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_laps.schema as activity_laps_schema
import modules.activities.activity_laps.service as activity_laps_service

router = APIRouter()


@router.get(
    "/laps",
    response_model=activity_laps_schema.ActivityLapsPage,
)
@core_rate_limit.limiter.limit(core_rate_limit.PUBLIC_READ)
def list_public_activity_laps(
    request: Request,
    activity_id: activity_dependencies.ActivityId,
    db: core_dependencies.DbSession,
    page: core_pagination.ChildPage,
) -> activity_laps_schema.ActivityLapsPage:
    """Return one page of public laps for an activity exposed via shareable link."""
    return activity_laps_service.list_public_activity_laps(
        activity_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )
