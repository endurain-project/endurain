"""Public (unauthenticated) routes for activity workout steps."""

from fastapi import APIRouter, Request

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema
import modules.activities.activity_workout_steps.service as activity_workout_steps_service

router = APIRouter()


@router.get(
    "/workout-steps",
    response_model=activity_workout_steps_schema.ActivityWorkoutStepsPage,
)
@core_rate_limit.limiter.limit(core_rate_limit.PUBLIC_READ)
def list_public_activity_workout_steps(
    request: Request,
    activity_id: activity_dependencies.ActivityId,
    db: core_dependencies.DbSession,
    page: core_pagination.ChildPage,
) -> activity_workout_steps_schema.ActivityWorkoutStepsPage:
    """Return one page of a publicly shared activity's workout steps."""
    return activity_workout_steps_service.list_public_activity_workout_steps(
        activity_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )
