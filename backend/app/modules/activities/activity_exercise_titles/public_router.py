"""Public API router for activity exercise titles."""

from fastapi import APIRouter

import core.dependencies as core_dependencies
import modules.activities.activity_exercise_titles.schema as activity_exercise_titles_schema
import modules.activities.activity_exercise_titles.service as activity_exercise_titles_service

router = APIRouter()


@router.get(
    "/all",
    response_model=list[activity_exercise_titles_schema.ActivityExerciseTitlesRead],
)
def list_public_activity_exercise_titles(
    db: core_dependencies.DbSession,
) -> list[activity_exercise_titles_schema.ActivityExerciseTitlesRead]:
    """Return all activity exercise titles via the public endpoint."""
    return activity_exercise_titles_service.list_public_activity_exercise_titles(db)
