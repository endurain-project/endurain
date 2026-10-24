"""Authenticated routes for activity workout steps."""

from typing import Annotated

from fastapi import APIRouter, Depends, Security

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema
import modules.activities.activity_workout_steps.service as activity_workout_steps_service
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "/workout-steps",
    response_model=activity_workout_steps_schema.ActivityWorkoutStepsPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def list_activity_workout_steps(
    activity_id: activity_dependencies.ActivityId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.child_page_params)],
) -> activity_workout_steps_schema.ActivityWorkoutStepsPage:
    """Return one page of the activity's workout steps, with the matching total."""
    return activity_workout_steps_service.list_activity_workout_steps(
        activity_id,
        token_user_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )
