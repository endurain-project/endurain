"""Application-layer orchestration for activity exercise titles.

Sits between the thin route and :mod:`crud`, matching the layering the activities
core uses. Exercise titles are a server-wide reference table rather than rows
hanging off one activity, so there is no per-activity visibility rule here — the
only access decision is the server-wide public-sharing setting, which gates the
anonymous read and belongs in this layer rather than in ``crud``.
"""

from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity_exercise_titles.crud as activity_exercise_titles_crud
import modules.activities.activity_exercise_titles.schema as activity_exercise_titles_schema
import modules.server_settings.integration_service as server_settings_integration

logger = core_logger.get_logger(__name__)


def list_activity_exercise_titles(
    db: Session,
) -> list[activity_exercise_titles_schema.ActivityExerciseTitles]:
    """Return every exercise title for an authenticated caller.

    Args:
        db: Database session.

    Returns:
        Every exercise title, empty when there are none.
    """
    return activity_exercise_titles_crud.get_activity_exercise_titles(db)


def list_public_activity_exercise_titles(
    db: Session,
) -> list[activity_exercise_titles_schema.ActivityExerciseTitles]:
    """Return every exercise title for an anonymous caller.

    Args:
        db: Database session.

    Returns:
        Every exercise title, empty when public shareable links are disabled
        server-wide.
    """
    if not server_settings_integration.public_shareable_links_enabled(db):
        logger.debug("Public exercise-title read denied: shareable links are disabled")
        return []
    return activity_exercise_titles_crud.get_activity_exercise_titles(db)
