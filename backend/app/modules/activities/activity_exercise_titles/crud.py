"""Activity exercise titles CRUD operations."""

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

import modules.activities.activity_exercise_titles.contracts as activity_exercise_titles_contracts
import modules.activities.activity_exercise_titles.models as activity_exercise_titles_models
import modules.activities.activity_exercise_titles.schema as activity_exercise_titles_schema
import modules.activities.activity_exercise_titles.serializers as activity_exercise_titles_serializers


def get_activity_exercise_titles(
    db: Session,
) -> list[activity_exercise_titles_schema.ActivityExerciseTitlesRead]:
    """Retrieve all activity exercise titles.

    Args:
        db: Database session.

    Returns:
        Every exercise title, empty when there are none.
    """
    stmt = select(activity_exercise_titles_models.ActivityExerciseTitles)
    return [activity_exercise_titles_serializers.to_read_schema(title) for title in db.execute(stmt).scalars().all()]


def get_activity_exercise_titles_page(
    db: Session, *, limit: int, offset: int
) -> list[activity_exercise_titles_schema.ActivityExerciseTitlesRead]:
    """Retrieve one window of the exercise titles, in id order.

    Args:
        db: Database session.
        limit: The most titles to return.
        offset: How many titles to skip.

    Returns:
        The titles in the window.
    """
    stmt = (
        select(activity_exercise_titles_models.ActivityExerciseTitles)
        .order_by(activity_exercise_titles_models.ActivityExerciseTitles.id)
        .limit(limit)
        .offset(offset)
    )
    return [activity_exercise_titles_serializers.to_read_schema(title) for title in db.execute(stmt).scalars().all()]


def count_activity_exercise_titles(db: Session) -> int:
    """Count the exercise titles.

    Args:
        db: Database session.

    Returns:
        The number of stored titles.
    """
    return db.execute(select(func.count(activity_exercise_titles_models.ActivityExerciseTitles.id))).scalar_one()


def create_activity_exercise_titles(
    activity_exercise_titles: list[activity_exercise_titles_contracts.ActivityExerciseTitlesCreate],
    db: Session,
) -> None:
    """Stage activity exercise titles, skipping pairs that already exist.

    The ``(exercise_category, exercise_name)`` unique constraint decides what is
    skipped, so repeats within the batch and rows inserted by a concurrent import
    are dropped rather than failing the caller's transaction.

    Args:
        activity_exercise_titles: Schemas to insert.
        db: Database session.
    """
    if not activity_exercise_titles:
        return

    stmt = (
        insert(activity_exercise_titles_models.ActivityExerciseTitles)
        .values(
            [
                {
                    "exercise_category": title.exercise_category,
                    "exercise_name": title.exercise_name,
                    "wkt_step_name": title.wkt_step_name,
                }
                for title in activity_exercise_titles
            ]
        )
        .on_conflict_do_nothing(constraint="uq_activity_exercise_titles_category_name")
    )
    db.execute(stmt)
