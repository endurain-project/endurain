"""Application-layer orchestration for activity laps.

Sits between the thin route and :mod:`crud`, matching the layering the activities
core uses. It owns the access decision — delegated to the shared
:mod:`modules.activities.activity.child_access` gate — so ``crud`` is left with
nothing but persistence, and so "who may read an activity's laps?" is answered in
the layer a reviewer looks at rather than inline above a ``SELECT``.
"""

from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity.child_access as activity_child_access
import modules.activities.activity_laps.crud as activity_laps_crud
import modules.activities.activity_laps.schema as activity_laps_schema

logger = core_logger.get_logger(__name__)

# The parent activity flag that hides laps from a non-owner.
_HIDE_ATTR = "hide_laps"


def list_activity_laps(
    activity_id: int,
    requester_user_id: int,
    db: Session,
) -> list[activity_laps_schema.ActivityLapsRead]:
    """Return an activity's laps for an authenticated caller.

    Args:
        activity_id: The parent activity.
        requester_user_id: The authenticated caller.
        db: Database session.

    Returns:
        The activity's laps, empty when the activity is not visible to the
        caller, its laps are hidden, or it has none. A collection read answers
        with a collection; the three cases are deliberately indistinguishable so
        the endpoint cannot be used to probe which activities exist.
    """
    if not activity_child_access.may_read_child(activity_id, requester_user_id, db, hide_attr=_HIDE_ATTR):
        return []
    return activity_laps_crud.get_activity_laps(activity_id, db)


def list_public_activity_laps(
    activity_id: int,
    db: Session,
) -> list[activity_laps_schema.ActivityLapsRead]:
    """Return a publicly shared activity's laps for an anonymous caller.

    Args:
        activity_id: The parent activity.
        db: Database session.

    Returns:
        The activity's laps, empty when it is not found, hidden, or not publicly
        visible — indistinguishable on purpose, since this endpoint is
        unauthenticated.
    """
    if not activity_child_access.may_read_public_child(activity_id, db, hide_attr=_HIDE_ATTR):
        return []
    return activity_laps_crud.get_activity_laps(activity_id, db)
