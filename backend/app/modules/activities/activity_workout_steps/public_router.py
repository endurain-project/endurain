"""Public (unauthenticated) routes for activity workout steps."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import core.database as core_database
import core.pagination as core_pagination
import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema
import modules.activities.activity_workout_steps.service as activity_workout_steps_service

router = APIRouter()


@router.get(
    "/workout-steps",
    response_model=activity_workout_steps_schema.ActivityWorkoutStepsPage,
)
def read_public_activity_workout_steps_all(
    activity_id: int,
    db: Annotated[Session, Depends(core_database.get_db)],
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.child_page_params)],
) -> activity_workout_steps_schema.ActivityWorkoutStepsPage:
    """Return one page of a publicly shared activity's workout steps.

    Args:
        activity_id: Activity primary key.
        db: Database session.
        page: Resolved paging window, capped so one request cannot ask for
            an unbounded number of rows.

    Returns:
        The page envelope. Empty when public sharing is disabled, the activity is
        not public, or the workout steps are hidden.
    """
    return activity_workout_steps_service.list_public_activity_workout_steps(
        activity_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )
