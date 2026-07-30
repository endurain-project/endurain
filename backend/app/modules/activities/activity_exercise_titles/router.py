"""Authenticated API router for activity exercise titles."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

import core.database as core_database
import modules.activities.activity_exercise_titles.crud as activity_exercise_titles_crud
import modules.activities.activity_exercise_titles.schema as activity_exercise_titles_schema
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "/all",
    response_model=list[activity_exercise_titles_schema.ActivityExerciseTitles] | None,
)
async def read_activities_exercise_titles_all(
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["activities:read"]),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[activity_exercise_titles_schema.ActivityExerciseTitles] | None:
    """
    Return all activity exercise titles.

    Args:
        _check_scopes: Scope check dependency for authorization.
        db: Database session.

    Returns:
        List of ActivityExerciseTitles or None when empty.

    Raises:
        HTTPException: If a database error occurs.
    """
    return activity_exercise_titles_crud.get_activity_exercise_titles(db)
