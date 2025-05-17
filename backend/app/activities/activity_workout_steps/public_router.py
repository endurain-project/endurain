from typing import Annotated, Callable

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import activities.activity_workout_steps.schema as activity_workout_steps_schema
import activities.activity_workout_steps.crud as activity_workout_steps_crud

import activities.activity.dependencies as activities_dependencies

import core.database as core_database

# Define the API router
router = APIRouter()


@router.get(
    "/activity_id/{activity_id}/all",
    response_model=list[activity_workout_steps_schema.ActivityWorkoutSteps] | None,
)
async def read_public_activities_workout_steps_for_activity_all(
    activity_id: int,
    validate_id: Annotated[
        Callable, Depends(activities_dependencies.validate_activity_id)
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the activity workout steps from the database and return them
    return activity_workout_steps_crud.get_public_activity_workout_steps(activity_id, db)