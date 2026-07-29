"""Activity exercise titles CRUD operations."""

from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.activities.activity_exercise_titles.models as activity_exercise_titles_models
import modules.activities.activity_exercise_titles.schema as activity_exercise_titles_schema
import modules.server_settings.utils as server_settings_utils

logger = core_logger.get_logger(__name__)


def _to_read_schema(
    orm_title: activity_exercise_titles_models.ActivityExerciseTitles,
) -> activity_exercise_titles_schema.ActivityExerciseTitles:
    """Convert an ORM row to its read schema so ORM never leaves ``crud``."""
    return activity_exercise_titles_schema.ActivityExerciseTitles.model_validate(orm_title)


@core_decorators.handle_db_errors
def get_activity_exercise_titles(
    db: Session,
) -> list[activity_exercise_titles_schema.ActivityExerciseTitles]:
    """
    Retrieve all activity exercise titles.

    Args:
        db: Database session.

    Returns:
        Every exercise title, empty when there are none.

    Raises:
        ProcessingError: If a database error occurs.
    """
    stmt = select(activity_exercise_titles_models.ActivityExerciseTitles)
    activity_exercise_titles = db.execute(stmt).scalars().all()

    if not activity_exercise_titles:
        return []

    return [_to_read_schema(title) for title in activity_exercise_titles]


@core_decorators.handle_db_errors
def get_public_activity_exercise_titles(
    db: Session,
) -> list[activity_exercise_titles_schema.ActivityExerciseTitles]:
    """
    Retrieve activity exercise titles when public sharing is enabled.

    Args:
        db: Database session.

    Returns:
        Every exercise title, empty when public links are disabled or there are
        no entries.

    Raises:
        HTTPException: If server settings are missing or a database
            error occurs.
    """
    server_settings = server_settings_utils.get_server_settings_or_404(db)

    if not server_settings.public_shareable_links:
        return []

    return get_activity_exercise_titles(db)


@core_decorators.handle_db_errors
def get_activity_exercise_title_by_exercise_name(
    exercise_name: int,
    db: Session,
) -> activity_exercise_titles_schema.ActivityExerciseTitles | None:
    """
    Retrieve a single activity exercise title by exercise name.

    Args:
        exercise_name: FIT exercise name identifier.
        db: Database session.

    Returns:
        Matching ActivityExerciseTitles or None if not found.

    Raises:
        ProcessingError: If a database error occurs.
    """
    stmt = select(activity_exercise_titles_models.ActivityExerciseTitles).where(
        activity_exercise_titles_models.ActivityExerciseTitles.exercise_name == exercise_name
    )
    row = db.execute(stmt).scalar_one_or_none()
    return _to_read_schema(row) if row is not None else None


@core_decorators.handle_db_errors
def create_activity_exercise_titles(
    activity_exercise_titles: list[activity_exercise_titles_schema.ActivityExerciseTitles],
    db: Session,
) -> None:
    """
    Insert activity exercise titles, skipping existing entries.

    Args:
        activity_exercise_titles: Schemas to insert.
        db: Database session.

    Returns:
        None.

    Raises:
        ConflictError: On a duplicate (exercise_name, exercise_category) entry.
        ProcessingError: On other database errors.
    """
    if not activity_exercise_titles:
        return

    model = activity_exercise_titles_models.ActivityExerciseTitles

    incoming_keys = {(t.exercise_name, t.exercise_category) for t in activity_exercise_titles}

    existing_stmt = select(model.exercise_name, model.exercise_category).where(
        tuple_(model.exercise_name, model.exercise_category).in_(incoming_keys)
    )
    existing_keys = set(db.execute(existing_stmt).all())

    new_entries = [
        model(
            exercise_category=t.exercise_category,
            exercise_name=t.exercise_name,
            wkt_step_name=t.wkt_step_name,
        )
        for t in activity_exercise_titles
        if (t.exercise_name, t.exercise_category) not in existing_keys
    ]

    if not new_entries:
        return

    try:
        db.add_all(new_entries)
        db.commit()
        logger.debug(
            "Inserted new activity exercise titles",
            extra=core_logger.context(inserted=len(new_entries), skipped=len(incoming_keys) - len(new_entries)),
        )
    except IntegrityError as integrity_error:
        db.rollback()
        logger.warning(
            "Activity exercise title insert conflicted on (exercise_name, exercise_category)",
            exc_info=integrity_error,
            extra=core_logger.context(attempted=len(new_entries)),
        )
        raise core_exceptions.ConflictError(
            "Duplicate entry error. Check if (exercise_name, exercise_category) is unique"
        ) from integrity_error
