from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import activities.activity_exercise_titles.schema as activity_exercise_titles_schema
import activities.activity_exercise_titles.crud as activity_exercise_titles_crud

import core.database as core_database

# Define the API router
router = APIRouter()


@router.get(
    "/all",
    response_model=list[activity_exercise_titles_schema.ActivityExerciseTitles] | None,
)
async def read_public_activities_laps_for_activity_all(
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the exercise titles from the database and return them
    return activity_exercise_titles_crud.get_public_activity_exercise_titles(db)