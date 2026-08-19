"""Public operations for activity exercise-title reference data."""

from sqlalchemy.orm import Session

import modules.activities.activity_exercise_titles.crud as exercise_titles_crud
import modules.activities.activity_exercise_titles.schema as exercise_titles_schema


def list_exercise_titles(db: Session) -> list[exercise_titles_schema.ActivityExerciseTitles]:
    """Return every exercise-title reference row."""
    return exercise_titles_crud.get_activity_exercise_titles(db)


def store_exercise_titles(
    titles: list[exercise_titles_schema.ActivityExerciseTitles],
    db: Session,
) -> None:
    """Store exercise-title reference rows, skipping existing entries."""
    exercise_titles_crud.create_activity_exercise_titles(titles, db)
