"""Public API router for activity exercise titles."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import core.database as core_database
import modules.activities.activity_exercise_titles.crud as activity_exercise_titles_crud
import modules.activities.activity_exercise_titles.schema as activity_exercise_titles_schema

router = APIRouter()


@router.get(
    "/all",
    response_model=list[activity_exercise_titles_schema.ActivityExerciseTitles],
)
def read_public_activities_exercise_titles_all(
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[activity_exercise_titles_schema.ActivityExerciseTitles]:
    """
    Return all activity exercise titles via the public endpoint.

    Args:
        db: Database session.

    Returns:
        List of ActivityExerciseTitles, or None if public sharable
        links are disabled or no entries exist.

    Raises:
        HTTPException: If server settings are missing or a database
            error occurs.
    """
    return activity_exercise_titles_crud.get_public_activity_exercise_titles(db)
