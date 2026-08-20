"""Public persistence operations for activity workout sets."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_sets.crud as activity_sets_crud
import modules.activities.activity_sets.schema as activity_sets_schema
import modules.activities.contributors as activity_contributors


def list_sets_for_activities(
    activity_ids: list[int],
    db: Session,
) -> list[activity_sets_schema.ActivitySetsRead]:
    """Return workout sets for activity IDs already scoped by the caller."""
    return activity_sets_crud.get_activities_sets(activity_ids, db)


def store_sets(
    sets: Sequence[activity_sets_schema.ActivitySetsCreate | list],
    activity_id: int,
    db: Session,
    *,
    commit: bool = True,
) -> None:
    """Store parsed workout sets for an activity."""
    activity_sets_crud.create_activity_sets(list(sets), activity_id, db, commit=commit)


def persist_ingestion_component(
    data: Any,
    activity: activity_schema.Activity,
    db: Session,
    *,
    commit: bool,
) -> None:
    """Persist parsed set data through the generic ingestion contract."""
    if activity.id is None:
        raise core_exceptions.ProcessingError("Cannot store sets before the activity has an id")
    store_sets(data, activity.id, db, commit=commit)


def ingestion_contributor() -> activity_contributors.ActivityIngestionContributor:
    """Return the activity-sets ingestion contribution."""
    return activity_contributors.ActivityIngestionContributor(
        key="sets",
        persist=persist_ingestion_component,
    )


def restore_profile_records(
    records: list[dict[str, Any]],
    original_activity_id: int,
    new_activity: activity_schema.Activity,
    db: Session,
) -> int:
    """Validate and restore profile set records for one activity."""
    if new_activity.id is None:
        return 0

    sets: list[activity_sets_schema.ActivitySetsCreate] = []
    for record in records:
        if record.get("activity_id") != original_activity_id:
            continue
        data = dict(record)
        data.pop("id", None)
        data["activity_id"] = new_activity.id
        sets.append(activity_sets_schema.ActivitySetsCreate.model_validate(data))

    if sets:
        store_sets(sets, new_activity.id, db)
    return len(sets)


def profile_contributor() -> activity_contributors.ProfileActivityContributor:
    """Return the activity-sets profile contribution."""
    return activity_contributors.ProfileActivityContributor(
        key="sets",
        archive_path="data/activity_sets.json",
        count_key="activity_sets",
        split=True,
        export=list_sets_for_activities,
        restore=restore_profile_records,
    )
