"""Public operations for activity exercise-title reference data."""

from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity_exercise_titles.crud as exercise_titles_crud
import modules.activities.activity_exercise_titles.schema as exercise_titles_schema
import modules.activities.contributors as activity_contributors

logger = core_logger.get_logger(__name__)


def _list_exercise_titles(db: Session) -> list[exercise_titles_schema.ActivityExerciseTitles]:
    """Return every exercise-title reference row."""
    return exercise_titles_crud.get_activity_exercise_titles(db)


def _store_exercise_titles(
    titles: list[exercise_titles_schema.ActivityExerciseTitles],
    db: Session,
) -> None:
    """Store exercise-title reference rows, skipping existing entries."""
    exercise_titles_crud.create_activity_exercise_titles(titles, db)


def _persist_file_ingestion_component(data: Any, db: Session) -> None:
    """Persist exercise titles through the generic file-ingestion contract."""
    _store_exercise_titles(data, db)


def ingestion_contributor() -> activity_contributors.FileIngestionContributor:
    """Return the exercise-title file-ingestion contribution."""
    return activity_contributors.FileIngestionContributor(
        key="exercise_titles",
        persist=_persist_file_ingestion_component,
    )


def _restore_profile_records(records: list[dict[str, Any]], db: Session) -> int:
    """Validate and restore all profile exercise-title records."""
    titles: list[exercise_titles_schema.ActivityExerciseTitles] = []
    for record in records:
        if not isinstance(record, dict):
            logger.warning("Skipping non-object exercise-title profile record")
            continue
        data = dict(record)
        data.pop("id", None)
        try:
            titles.append(exercise_titles_schema.ActivityExerciseTitles.model_validate(data))
        except ValidationError as err:
            logger.warning("Skipping invalid exercise-title profile record", exc_info=err)

    if titles:
        _store_exercise_titles(titles, db)
    return len(titles)


def profile_global_contributor() -> activity_contributors.ProfileGlobalContributor:
    """Return the exercise-title global profile contribution."""
    return activity_contributors.ProfileGlobalContributor(
        key="exercise_titles",
        archive_path="data/activity_exercise_titles.json",
        count_key="activity_exercise_titles",
        export=_list_exercise_titles,
        restore=_restore_profile_records,
    )
