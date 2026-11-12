"""Application logic for the combined activity detail.

Resolves the activity once, as the viewer may see it, and reads each child collection for that
activity, instead of every collection re-resolving the parent to decide the same access question.
What each child declares (its hide flag, its rows) stays in its own package.
"""

import uuid

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_detail.schema as activity_detail_schema
import modules.activities.activity_laps.integration_service as activity_laps_integration
import modules.activities.activity_sets.integration_service as activity_sets_integration
import modules.activities.activity_workout_steps.integration_service as activity_workout_steps_integration
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema


def get_activity_detail(
    activity_id: uuid.UUID, requester_user_id: int, db: Session
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
    activity = activity_integration.with_media(activity, requester_user_id, db)
    owner = (
        users_integration.list_public_profiles({activity.user_id}, db).get(activity.user_id)
        if activity.user_id
        else None
    )
    return _with_children(activity, owner, requester_user_id, db)


def get_public_activity_detail(activity_id: uuid.UUID, db: Session) -> activity_detail_schema.ActivityDetailRead:
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
    return _with_children(activity, _public_owner(activity.user_id, db) if activity.user_id else None, None, db)


def _public_owner(owner_id: int, db: Session) -> users_schema.UserPublicRead | None:
    """Return the owner an anonymous viewer may see, or ``None`` when the server does not show them.

    Args:
        owner_id: The owner of a publicly shared activity.
        db: Database session.

    Returns:
        The owner's public profile, or ``None`` when public user info is not shared or the owner is
        inactive or awaiting approval.
    """
    try:
        return users_integration.get_public_user(owner_id, db)
    except core_exceptions.NotFoundError:
        return None


def _with_children(
    activity: activity_schema.ActivityRead,
    owner: users_schema.UserPublicRead | None,
    requester_user_id: int | None,
    db: Session,
) -> activity_detail_schema.ActivityDetailRead:
    """Read each child collection for an activity the viewer may see.

    Args:
        activity: The activity, as the viewer is allowed to see it.
        owner: The owner's public profile as the viewer may see it, or ``None``.
        requester_user_id: The authenticated viewer, or ``None`` for an anonymous one.
        db: Database session.

    Returns:
        The detail.
    """
    return activity_detail_schema.ActivityDetailRead(
        activity=activity,
        owner=owner,
        laps=activity_laps_integration.list_for_activity(activity, requester_user_id, db),
        sets=activity_sets_integration.list_for_activity(activity, requester_user_id, db),
        workout_steps=activity_workout_steps_integration.list_for_activity(activity, requester_user_id, db),
    )
