"""Application-layer orchestration for activity workout sets.

Sits between the thin route and :mod:`crud`, matching the layering the activities
core uses. It owns the access decision — delegated to the shared
:mod:`modules.activities.activity.child_access` gate — so ``crud`` is left with
nothing but persistence.
"""

from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity.child_access as activity_child_access
import modules.activities.activity_sets.crud as activity_sets_crud
import modules.activities.activity_sets.schema as activity_sets_schema

logger = core_logger.get_logger(__name__)

# The parent activity flag that hides sets (and workout steps) from a non-owner.
_HIDE_ATTR = "hide_workout_sets_steps"


def list_activity_sets(
    activity_id: int,
    requester_user_id: int,
    db: Session,
) -> list[activity_sets_schema.ActivitySetsRead]:
    """Return an activity's workout sets for an authenticated caller.

    Args:
        activity_id: The parent activity.
        requester_user_id: The authenticated caller.
        db: Database session.

    Returns:
        The activity's sets, empty when the activity is not visible to the
        caller, its sets are hidden, or it has none — indistinguishable on
        purpose, so the endpoint cannot be used to probe which activities exist.
    """
    if not activity_child_access.may_read_child(activity_id, requester_user_id, db, hide_attr=_HIDE_ATTR):
        return []
    return activity_sets_crud.get_activity_sets(activity_id, db)


def list_public_activity_sets(
    activity_id: int,
    db: Session,
) -> list[activity_sets_schema.ActivitySetsRead]:
    """Return a publicly shared activity's workout sets for an anonymous caller.

    Args:
        activity_id: The parent activity.
        db: Database session.

    Returns:
        The activity's sets, empty when it is not found, hidden, or not publicly
        visible.
    """
    if not activity_child_access.may_read_public_child(activity_id, db, hide_attr=_HIDE_ATTR):
        return []
    return activity_sets_crud.get_activity_sets(activity_id, db)
