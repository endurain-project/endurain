"""Authenticated API router for activity exercise titles."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

import core.database as core_database
import modules.activities.activity_exercise_titles.schema as activity_exercise_titles_schema
import modules.activities.activity_exercise_titles.service as activity_exercise_titles_service
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "/all",
    response_model=list[activity_exercise_titles_schema.ActivityExerciseTitlesRead],
)
def list_activity_exercise_titles(
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["activities:read"]),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[activity_exercise_titles_schema.ActivityExerciseTitlesRead]:
    """Return all activity exercise titles."""
    return activity_exercise_titles_service.list_activity_exercise_titles(db)
