"""Application-layer orchestration for activity workout steps.

Sits between the thin route and :mod:`crud`, matching the layering the activities
core uses. It owns the access decision — delegated to the shared
:mod:`modules.activities.activity.child_access` gate — so ``crud`` is left with
nothing but persistence.

Reads are paginated: a structured workout's step count has no domain ceiling, so the previous "return every row" read
put no ceiling on the work or the payload one request could ask for.
"""

from sqlalchemy.orm import Session

import core.logger as core_logger
import core.pagination as core_pagination
import modules.activities.activity.child_access as activity_child_access
import modules.activities.activity_workout_steps.crud as activity_workout_steps_crud
import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema

logger = core_logger.get_logger(__name__)

# The parent activity flag that hides steps from a non-owner.
_HIDE_ATTR = "hide_workout_sets_steps"


def _page(
    items, total: int, page_number: int, num_records: int
) -> activity_workout_steps_schema.ActivityWorkoutStepsPage:
    """Assemble the page envelope."""
    return activity_workout_steps_schema.ActivityWorkoutStepsPage.build(items, total, page_number, num_records)


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
    if not activity_child_access.may_read_child(activity_id, requester_user_id, db, hide_attr=_HIDE_ATTR):
        logger.debug(
            "Refused a workout steps read; answering with an empty page",
            extra=core_logger.context(activity_id=activity_id, requester_user_id=requester_user_id),
        )
        return _page([], 0, page_number, num_records)
    items = activity_workout_steps_crud.get_activity_workout_steps(
        activity_id, db, page_number=page_number, num_records=num_records
    )
    total = activity_workout_steps_crud.count_activity_workout_steps(activity_id, db)
    return _page(items, total, page_number, num_records)


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
    if not activity_child_access.may_read_public_child(activity_id, db, hide_attr=_HIDE_ATTR):
        logger.debug(
            "Refused a public workout steps read; answering with an empty page",
            extra=core_logger.context(activity_id=activity_id),
        )
        return _page([], 0, page_number, num_records)
    items = activity_workout_steps_crud.get_activity_workout_steps(
        activity_id, db, page_number=page_number, num_records=num_records
    )
    total = activity_workout_steps_crud.count_activity_workout_steps(activity_id, db)
    return _page(items, total, page_number, num_records)
