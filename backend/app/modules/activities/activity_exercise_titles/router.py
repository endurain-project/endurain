"""Authenticated API router for activity exercise titles."""

from fastapi import APIRouter, Security

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import modules.activities.activity_exercise_titles.schema as activity_exercise_titles_schema
import modules.activities.activity_exercise_titles.service as activity_exercise_titles_service
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "",
    response_model=activity_exercise_titles_schema.ActivityExerciseTitlesPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def list_activity_exercise_titles(
    page: core_pagination.ChildPage,
    db: core_dependencies.DbSession,
) -> activity_exercise_titles_schema.ActivityExerciseTitlesPage:
    """Return one page of the activity exercise titles.

    Args:
        page: The requested window; a page holds up to the maximum when no size is given.
        db: Database session dependency.

    Returns:
        The page of exercise titles.
    """
    return activity_exercise_titles_service.list_activity_exercise_titles(page, db)
