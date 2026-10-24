"""Authenticated API router for activity exercise titles."""

from fastapi import APIRouter, Security

import core.dependencies as core_dependencies
import modules.activities.activity_exercise_titles.schema as activity_exercise_titles_schema
import modules.activities.activity_exercise_titles.service as activity_exercise_titles_service
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "/all",
    response_model=list[activity_exercise_titles_schema.ActivityExerciseTitlesRead],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def list_activity_exercise_titles(
    db: core_dependencies.DbSession,
) -> list[activity_exercise_titles_schema.ActivityExerciseTitlesRead]:
    """Return all activity exercise titles."""
    return activity_exercise_titles_service.list_activity_exercise_titles(db)
