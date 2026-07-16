"""Activity exercise titles CRUD operations."""

from fastapi import HTTPException, status
from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import modules.activities.activity_exercise_titles.models as activity_exercise_titles_models
import modules.activities.activity_exercise_titles.schema as activity_exercise_titles_schema
import modules.server_settings.utils as server_settings_utils


@core_decorators.handle_db_errors
def get_activity_exercise_titles(
    db: Session,
) -> list[activity_exercise_titles_models.ActivityExerciseTitles] | None:
    """
    Retrieve all activity exercise titles.

    Args:
        db: Database session.

    Returns:
        List of ActivityExerciseTitles or None when empty.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(activity_exercise_titles_models.ActivityExerciseTitles)
    activity_exercise_titles = db.execute(stmt).scalars().all()

    if not activity_exercise_titles:
        return None

    return list(activity_exercise_titles)


@core_decorators.handle_db_errors
def get_public_activity_exercise_titles(
    db: Session,
) -> list[activity_exercise_titles_models.ActivityExerciseTitles] | None:
    """
    Retrieve activity exercise titles when public sharing is enabled.

    Args:
        db: Database session.

    Returns:
        List of ActivityExerciseTitles, or None if public links
        are disabled or no entries exist.

    Raises:
        HTTPException: If server settings are missing or a database
            error occurs.
    """
    server_settings = server_settings_utils.get_server_settings_or_404(db)

    if not server_settings.public_shareable_links:
        return None

    return get_activity_exercise_titles(db)


@core_decorators.handle_db_errors
def get_activity_exercise_title_by_exercise_name(
    exercise_name: int,
    db: Session,
) -> activity_exercise_titles_models.ActivityExerciseTitles | None:
    """
    Retrieve a single activity exercise title by exercise name.

    Args:
        exercise_name: FIT exercise name identifier.
        db: Database session.

    Returns:
        Matching ActivityExerciseTitles or None if not found.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(activity_exercise_titles_models.ActivityExerciseTitles).where(
        activity_exercise_titles_models.ActivityExerciseTitles.exercise_name == exercise_name
    )
    return db.execute(stmt).scalar_one_or_none()


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
        HTTPException: 409 on duplicate entry conflict, 500 on
            other database errors.
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
    except IntegrityError as integrity_error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("Duplicate entry error. Check if (exercise_name, exercise_category) is unique"),
        ) from integrity_error
