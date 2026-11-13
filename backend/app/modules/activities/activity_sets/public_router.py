"""Public (unauthenticated) routes for activity workout sets."""

from fastapi import APIRouter, Request

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_sets.schema as activity_sets_schema
import modules.activities.activity_sets.service as activity_sets_service

router = APIRouter()


@router.get(
    "/sets",
    response_model=activity_sets_schema.ActivitySetsPage,
)
@core_rate_limit.limiter.limit(core_rate_limit.PUBLIC_READ)
def list_public_activity_sets(
    request: Request,
    activity_id: activity_dependencies.ActivityId,
    db: core_dependencies.DbSession,
    page: core_pagination.ChildPage,
) -> activity_sets_schema.ActivitySetsPage:
    """Return one page of a publicly shared activity's sets."""
    return activity_sets_service.list_public_activity_sets(
        activity_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )
