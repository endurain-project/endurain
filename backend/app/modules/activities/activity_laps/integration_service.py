"""Public persistence operations for activity laps."""

from typing import Any

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_laps.crud as activity_laps_crud
import modules.activities.activity_laps.schema as activity_laps_schema
import modules.activities.contributors as activity_contributors


def list_laps_for_activities(
    activity_ids: list[int],
    db: Session,
) -> list[activity_laps_schema.ActivityLapsRead]:
    """Return laps for activity IDs already scoped by the caller."""
    return activity_laps_crud.get_activities_laps(activity_ids, db)


def store_laps(
    laps: list[dict],
    activity_id: int,
    db: Session,
    *,
    commit: bool = True,
) -> None:
    """Store parsed laps for an activity."""
    activity_laps_crud.create_activity_laps(laps, activity_id, db, commit=commit)


def persist_ingestion_component(
    data: Any,
    activity: activity_schema.Activity,
    db: Session,
    *,
    commit: bool,
) -> None:
    """Persist parsed lap data through the generic ingestion contract."""
    if activity.id is None:
        raise core_exceptions.ProcessingError("Cannot store laps before the activity has an id")
    store_laps(data, activity.id, db, commit=commit)


def ingestion_contributor() -> activity_contributors.ActivityIngestionContributor:
    """Return the activity-laps ingestion contribution."""
    return activity_contributors.ActivityIngestionContributor(
        key="laps",
        persist=persist_ingestion_component,
    )


def restore_profile_records(
    records: list[dict[str, Any]],
    original_activity_id: int,
    new_activity: activity_schema.Activity,
    db: Session,
) -> int:
    """Validate and restore profile lap records for one activity."""
    if new_activity.id is None:
        return 0

    laps: list[dict[str, Any]] = []
    for record in records:
        if record.get("activity_id") != original_activity_id:
            continue
        data = dict(record)
        data.pop("id", None)
        data.pop("activity_id", None)
        lap = activity_laps_schema.ActivityLapsBase.model_validate(data)
        laps.append(lap.model_dump())

    if laps:
        store_laps(laps, new_activity.id, db)
    return len(laps)


def profile_contributor() -> activity_contributors.ProfileActivityContributor:
    """Return the activity-laps profile contribution."""
    return activity_contributors.ProfileActivityContributor(
        key="laps",
        archive_path="data/activity_laps.json",
        count_key="activity_laps",
        split=True,
        export=list_laps_for_activities,
        restore=restore_profile_records,
    )
