"""Application-layer orchestration for activity exercise titles.

Sits between the thin route and :mod:`crud`, matching the layering the activities
core uses. Exercise titles are a server-wide reference table rather than rows
hanging off one activity, so there is no per-activity visibility rule here — the
only access decision is the server-wide public-sharing setting, which gates the
anonymous read and belongs in this layer rather than in ``crud``.
"""

from sqlalchemy.orm import Session

import core.logger as core_logger
import core.pagination as core_pagination
import modules.activities.activity_exercise_titles.crud as activity_exercise_titles_crud
import modules.activities.activity_exercise_titles.schema as activity_exercise_titles_schema
import modules.server_settings.integration_service as server_settings_integration

logger = core_logger.get_logger(__name__)


def _page(page: core_pagination.PageParams, db: Session) -> activity_exercise_titles_schema.ActivityExerciseTitlesPage:
    """Read one page of the exercise titles with the total.

    Args:
        page: The requested window.
        db: Database session.

    Returns:
        The page.
    """
    titles = activity_exercise_titles_crud.get_activity_exercise_titles_page(
        db, limit=page.num_records, offset=(page.page_number - 1) * page.num_records
    )
    total = activity_exercise_titles_crud.count_activity_exercise_titles(db)
    return activity_exercise_titles_schema.ActivityExerciseTitlesPage.build(
        titles, total, page.page_number, page.num_records
    )


def list_activity_exercise_titles(
    page: core_pagination.PageParams, db: Session
) -> activity_exercise_titles_schema.ActivityExerciseTitlesPage:
    """Return one page of the exercise titles for an authenticated caller.

    Args:
        page: The requested window.
        db: Database session.

    Returns:
        The page, empty when there are none.
    """
    return _page(page, db)


def list_public_activity_exercise_titles(
    page: core_pagination.PageParams, db: Session
) -> activity_exercise_titles_schema.ActivityExerciseTitlesPage:
    """Return one page of the exercise titles for an anonymous caller.

    Args:
        page: The requested window.
        db: Database session.

    Returns:
        The page, empty when public shareable links are disabled server-wide.
    """
    if not server_settings_integration.public_shareable_links_enabled(db):
        logger.debug("Public exercise-title read denied: shareable links are disabled")
        return activity_exercise_titles_schema.ActivityExerciseTitlesPage.build(
            [], 0, page.page_number, page.num_records
        )
    return _page(page, db)
