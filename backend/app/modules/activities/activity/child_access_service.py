"""The one authorization gate for reading an activity's child sub-resources.

Laps, sets, streams and workout steps are all "rows hanging off an activity", and
the question "may this caller read them?" has the same answer for all four: the
caller must be able to see the parent activity, and the parent's ``hide_*`` flag
guarding that particular child must not be set against a non-owner.

The rule lives here once, not in each child CRUD, so a fix cannot land in three
of the four places and the child modules follow the same router -> service ->
crud layering the activities core does.

Each gate resolves the parent as the caller may see it, because a child that repeats
the parent's data (a lap's start time and position, a stream's samples) has to be
masked by the parent's other ``hide_*`` flags too, not only by the one guarding it.

It also holds the one owner-visibility rule for the activities module: another user's
activities are never shown while that user is inactive or awaiting approval.
"""

import uuid

from sqlalchemy.orm import Session

import modules.activities.activity.crud as activity_crud
import modules.activities.activity.schema as activity_schema
import modules.followers.integration_service as followers_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration


def list_visible_followee_ids(requester_user_id: uuid.UUID, db: Session) -> list[uuid.UUID]:
    """Return the accepted followees of a user whose activities may be shown to them.

    A followee who is inactive or awaiting approval is left out, so the feed and every
    followers-only read skip that owner's activities.

    Args:
        requester_user_id: The authenticated caller.
        db: Database session.

    Returns:
        The requester's accepted-followee ids whose accounts are visible.
    """
    followee_ids = followers_integration.list_accepted_followee_ids(requester_user_id, db)
    if not followee_ids:
        return []
    visible = users_integration.list_public_profiles(followee_ids, db)
    return [followee_id for followee_id in followee_ids if followee_id in visible]


def is_owner_visible_to(owner_id: uuid.UUID | None, requester_user_id: uuid.UUID | None, db: Session) -> bool:
    """Return whether a viewer may see activities owned by ``owner_id`` at all.

    The owner always sees their own; anyone else, signed in or anonymous, only while the owner is
    active and approved.

    Args:
        owner_id: The owner of the activity, or ``None`` when it has none.
        requester_user_id: The authenticated caller, or ``None`` for an anonymous viewer.
        db: Database session.

    Returns:
        False when the owner is missing, inactive or awaiting approval.
    """
    if owner_id is None:
        return False
    return owner_id == requester_user_id or owner_id in users_integration.list_public_profiles({owner_id}, db)


def resolve_readable_parent(
    activity_id: uuid.UUID,
    requester_user_id: uuid.UUID,
    db: Session,
) -> activity_schema.ActivityRead | None:
    """Return the parent activity when an authenticated caller may see it at all.

    Unmasked, so the caller can read the ``hide_*`` flags it needs for its own
    per-field masking. Seeing the parent does not by itself grant access to any
    particular child — that is the caller's remaining decision.

    Args:
        activity_id: The parent activity.
        requester_user_id: The authenticated caller.
        db: Database session.

    Returns:
        The activity, or ``None`` when it does not exist, is not visible or its owner is not visible.
    """
    followee_ids = list_visible_followee_ids(requester_user_id, db)
    activity = activity_crud.get_viewable_activity_by_id_for_user(
        activity_id, requester_user_id, db, followee_ids=followee_ids
    )
    if activity is None or not is_owner_visible_to(activity.user_id, requester_user_id, db):
        return None
    return activity


def resolve_public_parent(activity_id: uuid.UUID, db: Session) -> activity_schema.ActivityRead | None:
    """Return the parent activity when it is publicly shareable.

    Enforces the server-wide ``public_shareable_links`` setting, ``visibility == 0``,
    ``is_hidden is False`` and a visible owner in one place.

    Args:
        activity_id: The parent activity.
        db: Database session.

    Returns:
        The visibility-masked public activity, or ``None``.
    """
    if not server_settings_integration.public_shareable_links_enabled(db):
        return None
    activity = activity_crud.get_activity_by_id_if_is_public(activity_id, db)
    if activity is None or not is_owner_visible_to(activity.user_id, None, db):
        return None
    return activity


def is_hidden_from(
    activity: activity_schema.ActivityRead, requester_user_id: uuid.UUID | None, *, hide_attr: str
) -> bool:
    """Return whether an activity's ``hide_*`` flag hides one of its children from a viewer.

    The owner is never hidden from; a non-owner, or an anonymous viewer (``None``), is whenever
    the flag is set. It decides from an activity the caller already holds, so it runs no query.

    Args:
        activity: The parent activity, as the viewer is allowed to see it.
        requester_user_id: The authenticated viewer, or ``None`` for an anonymous one.
        hide_attr: Name of the parent's boolean ``hide_*`` flag guarding the child.

    Returns:
        True when the child must be withheld from this viewer.
    """
    return requester_user_id != activity.user_id and bool(getattr(activity, hide_attr))
