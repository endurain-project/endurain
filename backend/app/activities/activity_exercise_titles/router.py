from typing import Annotated, Callable

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

import activities.activity_exercise_titles.schema as activity_exercise_titles_schema
import activities.activity_exercise_titles.crud as activity_exercise_titles_crud

import auth.security as auth_security

import core.database as core_database

# Define the API router
router = APIRouter()


@router.get(
    "/all",
    response_model=list[activity_exercise_titles_schema.ActivityExerciseTitles] | None,
)
async def read_activities_exercise_titles_all(
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the exercise titles from the database and return them
    return activity_exercise_titles_crud.get_activity_exercise_titles(db)
