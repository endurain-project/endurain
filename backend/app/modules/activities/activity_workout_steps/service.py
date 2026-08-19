"""Application-layer orchestration for activity workout steps.

Declares *what* an activity's workout steps are — the parent flag that hides them
and the two CRUD calls that read them — and delegates *how* the paged read runs
to the shared :mod:`modules.activities.activity.child_collection` seam, which
owns the access gate and the rule that a refusal and an empty collection answer
alike.

Reads are paginated: a structured workout's step count has no domain ceiling, so
the previous "return every row" read put no ceiling on the work or the payload
one request could ask for.
"""

from sqlalchemy.orm import Session

import core.pagination as core_pagination
import modules.activities.activity.integration_service as activity_child_collection
import modules.activities.activity_workout_steps.crud as activity_workout_steps_crud
import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema

_COLLECTION: activity_child_collection.ChildCollection[activity_workout_steps_schema.ActivityWorkoutStepsPage] = (
    activity_child_collection.ChildCollection(
        name="workout steps",
        hide_attr="hide_workout_sets_steps",
        fetch=activity_workout_steps_crud.get_activity_workout_steps,
        count=activity_workout_steps_crud.count_activity_workout_steps,
        build=activity_workout_steps_schema.ActivityWorkoutStepsPage.build,
    )
)


def list_activity_workout_steps(
    activity_id: int,
    requester_user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_CHILD_NUM_RECORDS,
) -> activity_workout_steps_schema.ActivityWorkoutStepsPage:
    """Return one page of activity workout steps for an authenticated caller.

    Args:
        activity_id: The parent activity.
        requester_user_id: The authenticated caller.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.

    Returns:
        The page envelope. An empty page when the activity is not visible to the
        caller, its steps are hidden, or it has none — deliberately
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


def list_public_activity_workout_steps(
    activity_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_CHILD_NUM_RECORDS,
) -> activity_workout_steps_schema.ActivityWorkoutStepsPage:
    """Return one page of a publicly shared activity's steps for an anonymous caller.

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
