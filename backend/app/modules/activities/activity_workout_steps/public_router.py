"""Activity workout steps public router."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import core.database as core_database
import modules.activities.activity.dependencies as activities_dependencies
import modules.activities.activity_workout_steps.crud as activity_workout_steps_crud
import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema

# Define the API router
router = APIRouter()


@router.get(
    "/activity_id/{activity_id}/all",
    response_model=(list[activity_workout_steps_schema.ActivityWorkoutSteps] | None),
)
async def read_public_activity_workout_steps_all(
    activity_id: int,
    _validate_id: Annotated[
        Callable,
        Depends(activities_dependencies.validate_activity_id),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Get all workout steps for a public activity.

    Returns:
        List of workout steps or None.
    """
    return activity_workout_steps_crud.get_public_activity_workout_steps(activity_id, db)
