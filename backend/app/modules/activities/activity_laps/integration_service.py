"""Contributor surface for activity laps."""

from typing import Any

from sqlalchemy.orm import Session

import modules.activities.activity_laps.crud as activity_laps_crud
import modules.activities.activity_laps.schema as activity_laps_schema
import modules.activities.contributors as activities_contributors


def _list_laps_for_activities(
    activity_ids: list[int],
    db: Session,
) -> list[activity_laps_schema.ActivityLapsRead]:
    """Return laps for activity IDs already scoped by the caller.

    Args:
        activity_ids: IDs of the activities to read.
        db: Database session.

    Returns:
        Laps for activity IDs already scoped by the caller.
    """
    return activity_laps_crud.get_activities_laps(activity_ids, db)


def _store_laps(
    laps: list[dict],
    activity_id: int,
    db: Session,
) -> None:
    """Store parsed laps for an activity.

    Args:
        laps: Laps to store.
        activity_id: ID of the parent activity.
        db: Database session.
    """
    activity_laps_crud.create_activity_laps(laps, activity_id, db)


def _parse_profile_record(record: dict[str, Any], _activity_id: int) -> dict[str, Any]:
    """Validate one archived lap record.

    Laps are stored from plain dicts and carry no parent id of their own, so the
    archived ``activity_id`` is dropped rather than re-keyed.

    Args:
        record: The archived record, without its ``id``.
        _activity_id: ID of the restored activity (unused: the store re-keys laps).

    Returns:
        The validated lap as a dict.
    """
    data = {key: value for key, value in record.items() if key != "activity_id"}
    return activity_laps_schema.ActivityLapsBase.model_validate(data).model_dump()


def ingestion_contributor() -> activities_contributors.ActivityIngestionContributor:
    """Return the activity-laps ingestion contribution.

    Returns:
        The contributor.
    """
    return activities_contributors.child_ingestion_contributor(key="laps", store=_store_laps)


def profile_contributor() -> activities_contributors.ProfileActivityContributor:
    """Return the activity-laps profile contribution.

    Returns:
        The contributor.
    """
    return activities_contributors.child_profile_contributor(
        key="laps",
        archive_path="data/activity_laps.json",
        count_key="activity_laps",
        split=True,
        export=_list_laps_for_activities,
        store=_store_laps,
        parse_record=_parse_profile_record,
    )
