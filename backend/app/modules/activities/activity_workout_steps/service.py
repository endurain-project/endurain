"""Application-layer orchestration for activity workout steps.

Sits between the thin route and :mod:`crud`, matching the layering the activities
core uses. It owns the access decision — delegated to the shared
:mod:`modules.activities.activity.child_access` gate — so ``crud`` is left with
nothing but persistence.
"""

from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity.child_access as activity_child_access
import modules.activities.activity_workout_steps.crud as activity_workout_steps_crud
import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema

logger = core_logger.get_logger(__name__)

# The parent activity flag that hides workout steps (and sets) from a non-owner.
_HIDE_ATTR = "hide_workout_sets_steps"


def list_activity_workout_steps(
    activity_id: int,
    requester_user_id: int,
    db: Session,
) -> list[activity_workout_steps_schema.ActivityWorkoutSteps]:
    """Return an activity's workout steps for an authenticated caller.

    Args:
        activity_id: The parent activity.
        requester_user_id: The authenticated caller.
        db: Database session.

    Returns:
        The activity's workout steps, empty when the activity is not visible to
        the caller, its steps are hidden, or it has none — indistinguishable on
        purpose, so the endpoint cannot be used to probe which activities exist.
    """
    if not activity_child_access.may_read_child(activity_id, requester_user_id, db, hide_attr=_HIDE_ATTR):
        return []
    return activity_workout_steps_crud.get_activity_workout_steps(activity_id, db)


def list_public_activity_workout_steps(
    activity_id: int,
    db: Session,
) -> list[activity_workout_steps_schema.ActivityWorkoutSteps]:
    """Return a publicly shared activity's workout steps for an anonymous caller.

    Args:
        activity_id: The parent activity.
        db: Database session.

    Returns:
        The activity's workout steps, empty when it is not found, hidden, or not
        publicly visible.
    """
    if not activity_child_access.may_read_public_child(activity_id, db, hide_attr=_HIDE_ATTR):
        return []
    return activity_workout_steps_crud.get_activity_workout_steps(activity_id, db)
