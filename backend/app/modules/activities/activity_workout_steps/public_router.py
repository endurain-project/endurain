"""Public (unauthenticated) routes for activity workout steps."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import core.database as core_database
import core.pagination as core_pagination
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema
import modules.activities.activity_workout_steps.service as activity_workout_steps_service

router = APIRouter()


@router.get(
    "/workout-steps",
    response_model=activity_workout_steps_schema.ActivityWorkoutStepsPage,
)
def list_public_activity_workout_steps(
    activity_id: activity_dependencies.ActivityId,
    db: Annotated[Session, Depends(core_database.get_db)],
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.child_page_params)],
) -> activity_workout_steps_schema.ActivityWorkoutStepsPage:
    """Return one page of a publicly shared activity's workout steps."""
    return activity_workout_steps_service.list_public_activity_workout_steps(
        activity_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )
