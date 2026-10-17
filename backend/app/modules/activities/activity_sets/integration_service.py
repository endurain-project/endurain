"""Public persistence operations for activity workout sets."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

import modules.activities.activity_sets.contracts as activity_sets_contracts
import modules.activities.activity_sets.crud as activity_sets_crud
import modules.activities.activity_sets.schema as activity_sets_schema
import modules.activities.contributors as activities_contributors


def _list_sets_for_activities(
    activity_ids: list[int],
    db: Session,
) -> list[activity_sets_schema.ActivitySetsRead]:
    """Return workout sets for activity IDs already scoped by the caller.

    Args:
        activity_ids: IDs of the activities to read.
        db: Database session.

    Returns:
        Workout sets for activity IDs already scoped by the caller.
    """
    return activity_sets_crud.get_activities_sets(activity_ids, db)


def _store_sets(
    sets: Sequence[activity_sets_contracts.ActivitySetsCreate | list],
    activity_id: int,
    db: Session,
) -> None:
    """Store parsed workout sets for an activity.

    Args:
        sets: Sets to store.
        activity_id: ID of the parent activity.
        db: Database session.
    """
    activity_sets_crud.create_activity_sets(list(sets), activity_id, db)


def _parse_profile_record(record: dict[str, Any], activity_id: int) -> activity_sets_contracts.ActivitySetsCreate:
    """Validate one archived set record onto the restored activity.

    Args:
        record: The archived record, without its ``id``.
        activity_id: ID of the activity the set is restored onto.

    Returns:
        The validated set.
    """
    return activity_sets_contracts.ActivitySetsCreate.model_validate({**record, "activity_id": activity_id})


def ingestion_contributor() -> activities_contributors.ActivityIngestionContributor:
    """Return the activity-sets ingestion contribution.

    Returns:
        The contributor.
    """
    return activities_contributors.child_ingestion_contributor(key="sets", store=_store_sets)


def profile_contributor() -> activities_contributors.ProfileActivityContributor:
    """Return the activity-sets profile contribution.

    Returns:
        The contributor.
    """
    return activities_contributors.child_profile_contributor(
        key="sets",
        archive_path="data/activity_sets.json",
        count_key="activity_sets",
        split=True,
        export=_list_sets_for_activities,
        store=_store_sets,
        parse_record=_parse_profile_record,
    )
