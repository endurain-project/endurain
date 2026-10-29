"""Public API router for activity exercise titles."""

from fastapi import APIRouter, Request

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.activities.activity_exercise_titles.schema as activity_exercise_titles_schema
import modules.activities.activity_exercise_titles.service as activity_exercise_titles_service

router = APIRouter()


@router.get(
    "",
    response_model=activity_exercise_titles_schema.ActivityExerciseTitlesPage,
)
@core_rate_limit.limiter.limit(core_rate_limit.PUBLIC_READ)
def list_public_activity_exercise_titles(
    request: Request,
    page: core_pagination.ChildPage,
    db: core_dependencies.DbSession,
) -> activity_exercise_titles_schema.ActivityExerciseTitlesPage:
    """Return one page of the activity exercise titles via the public endpoint.

    Args:
        request: The incoming request, read by the rate limiter.
        page: The requested window; a page holds up to the maximum when no size is given.
        db: Database session dependency.

    Returns:
        The page of exercise titles, empty when public shareable links are disabled.
    """
    return activity_exercise_titles_service.list_public_activity_exercise_titles(page, db)
