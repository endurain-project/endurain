"""Public API router for activity exercise titles."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import core.database as core_database
import modules.activities.activity_exercise_titles.schema as activity_exercise_titles_schema
import modules.activities.activity_exercise_titles.service as activity_exercise_titles_service

router = APIRouter()


@router.get(
    "/all",
    response_model=list[activity_exercise_titles_schema.ActivityExerciseTitlesRead],
)
def list_public_activity_exercise_titles(
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[activity_exercise_titles_schema.ActivityExerciseTitlesRead]:
    """Return all activity exercise titles via the public endpoint."""
    return activity_exercise_titles_service.list_public_activity_exercise_titles(db)
