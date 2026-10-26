"""Application logic for the combined activity detail.

Resolves the activity once, as the viewer may see it, and reads each child collection for that
activity, instead of every collection re-resolving the parent to decide the same access question.
What each child declares (its hide flag, its rows) stays in its own package.
"""

from sqlalchemy.orm import Session

import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_detail.schema as activity_detail_schema
import modules.activities.activity_laps.integration_service as activity_laps_integration
import modules.activities.activity_sets.integration_service as activity_sets_integration
import modules.activities.activity_workout_steps.integration_service as activity_workout_steps_integration


def get_activity_detail(
    activity_id: int, requester_user_id: int, db: Session
) -> activity_detail_schema.ActivityDetailRead:
    """Return an activity with its child collections for an authenticated viewer.

    Args:
        activity_id: The activity to read.
        requester_user_id: The authenticated caller.
        db: Database session.

    Returns:
        The activity and the first page of each child collection.

    Raises:
        NotFoundError: When the activity does not exist or is not visible to the caller.
    """
    activity = activity_integration.get_readable_activity(activity_id, requester_user_id, db)
    return _with_children(activity, requester_user_id, db)


def get_public_activity_detail(activity_id: int, db: Session) -> activity_detail_schema.ActivityDetailRead:
    """Return a publicly shared activity with its child collections for an anonymous viewer.

    Args:
        activity_id: The activity to read.
        db: Database session.

    Returns:
        The activity and the first page of each child collection.

    Raises:
        NotFoundError: When the activity does not exist or is not publicly shareable.
    """
    activity = activity_integration.get_public_activity(activity_id, db)
    return _with_children(activity, None, db)


def _with_children(
    activity: activity_schema.ActivityRead, requester_user_id: int | None, db: Session
) -> activity_detail_schema.ActivityDetailRead:
    """Read each child collection for an activity the viewer may see.

    Args:
        activity: The activity, as the viewer is allowed to see it.
        requester_user_id: The authenticated viewer, or ``None`` for an anonymous one.
        db: Database session.

    Returns:
        The detail.
    """
    return activity_detail_schema.ActivityDetailRead(
        activity=activity,
        laps=activity_laps_integration.list_for_activity(activity, requester_user_id, db),
        sets=activity_sets_integration.list_for_activity(activity, requester_user_id, db),
        workout_steps=activity_workout_steps_integration.list_for_activity(activity, requester_user_id, db),
    )
