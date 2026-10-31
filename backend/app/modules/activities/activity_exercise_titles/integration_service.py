"""Public operations for activity exercise-title reference data."""

from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity_exercise_titles.contracts as activity_exercise_titles_contracts
import modules.activities.activity_exercise_titles.crud as activity_exercise_titles_crud
import modules.activities.contributors as activities_contributors

logger = core_logger.get_logger(__name__)


def _persist_file_ingestion_component(data: Any, db: Session) -> None:
    """Persist exercise titles through the generic file-ingestion contract.

    Args:
        data: The parsed exercise titles.
        db: Database session.
    """
    activity_exercise_titles_crud.create_activity_exercise_titles(data, db)


def ingestion_contributor() -> activities_contributors.FileIngestionContributor:
    """Return the exercise-title file-ingestion contribution.

    Returns:
        The contributor.
    """
    return activities_contributors.FileIngestionContributor(
        key="exercise_titles",
        persist=_persist_file_ingestion_component,
    )


def _restore_profile_records(records: list[dict[str, Any]], db: Session) -> int:
    """Validate and restore all profile exercise-title records.

    Args:
        records: Profile records to restore.
        db: Database session.

    Returns:
        The number of records restored.
    """
    titles: list[activity_exercise_titles_contracts.ActivityExerciseTitlesCreate] = []
    for record in records:
        if not isinstance(record, dict):
            logger.warning("Skipping non-object exercise-title profile record")
            continue
        data = dict(record)
        data.pop("id", None)
        try:
            titles.append(activity_exercise_titles_contracts.ActivityExerciseTitlesCreate.model_validate(data))
        except ValidationError as err:
            logger.warning("Skipping invalid exercise-title profile record", exc_info=err)

    if titles:
        activity_exercise_titles_crud.create_activity_exercise_titles(titles, db)
    return len(titles)


def profile_global_contributor() -> activities_contributors.ProfileGlobalContributor:
    """Return the exercise-title global profile contribution.

    Returns:
        The contributor.
    """
    return activities_contributors.ProfileGlobalContributor(
        key="exercise_titles",
        archive_path="data/activity_exercise_titles.json",
        count_key="activity_exercise_titles",
        export=activity_exercise_titles_crud.get_activity_exercise_titles,
        restore=_restore_profile_records,
    )
