"""Application-layer orchestration for activity workout sets.

Declares *what* an activity's sets are — the parent flag that hides them and the
two CRUD calls that read them — and delegates *how* the paged read runs to the
shared :mod:`modules.activities.activity.child_collection` seam, which owns the
access gate and the rule that a refusal and an empty collection answer alike.

Reads are paginated: a strength session's set count has no domain ceiling, so the
previous "return every row" read put no ceiling on the work or the payload one
request could ask for.
"""

from sqlalchemy.orm import Session

import core.pagination as core_pagination
import modules.activities.activity.integration_service as activity_child_collection
import modules.activities.activity_sets.crud as activity_sets_crud
import modules.activities.activity_sets.schema as activity_sets_schema

_COLLECTION: activity_child_collection.ChildCollection[activity_sets_schema.ActivitySetsPage] = (
    activity_child_collection.ChildCollection(
        name="workout sets",
        hide_attr="hide_workout_sets_steps",
        fetch=activity_sets_crud.get_activity_sets,
        count=activity_sets_crud.count_activity_sets,
        build=activity_sets_schema.ActivitySetsPage.build,
    )
)


def list_activity_sets(
    activity_id: int,
    requester_user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_CHILD_NUM_RECORDS,
) -> activity_sets_schema.ActivitySetsPage:
    """Return one page of activity workout sets for an authenticated caller.

    Args:
        activity_id: The parent activity.
        requester_user_id: The authenticated caller.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.

    Returns:
        The page envelope. An empty page when the activity is not visible to the
        caller, its sets are hidden, or it has none — deliberately
        indistinguishable, so the endpoint cannot be used to probe which
        activities exist.
    """
    return _COLLECTION.list_for_requester(
        activity_id,
        requester_user_id,
        db,
        page_number=page_number,
        num_records=num_records,
    )


def list_public_activity_sets(
    activity_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_CHILD_NUM_RECORDS,
) -> activity_sets_schema.ActivitySetsPage:
    """Return one page of a publicly shared activity's sets for an anonymous caller.

    Args:
        activity_id: The parent activity.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.

    Returns:
        The page envelope, empty when the activity is not found, hidden, or not
        publicly visible.
    """
    return _COLLECTION.list_public(activity_id, db, page_number=page_number, num_records=num_records)
