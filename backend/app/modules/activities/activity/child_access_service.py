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
"""

from sqlalchemy.orm import Session

import modules.activities.activity.crud as activity_crud
import modules.activities.activity.schema as activity_schema
import modules.followers.integration_service as followers_integration
import modules.server_settings.integration_service as server_settings_integration


def resolve_readable_parent(
    activity_id: int,
    requester_user_id: int,
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
        The activity, or ``None`` when it does not exist or is not visible.
    """
    followee_ids = followers_integration.list_accepted_followee_ids(requester_user_id, db)
    return activity_crud.get_viewable_activity_by_id_for_user(
        activity_id, requester_user_id, db, followee_ids=followee_ids
    )


def resolve_public_parent(activity_id: int, db: Session) -> activity_schema.ActivityRead | None:
    """Return the parent activity when it is publicly shareable.

    Enforces the server-wide ``public_shareable_links`` setting, ``visibility == 0``
    and ``is_hidden is False`` in one place.

    Args:
        activity_id: The parent activity.
        db: Database session.

    Returns:
        The visibility-masked public activity, or ``None``.
    """
    if not server_settings_integration.public_shareable_links_enabled(db):
        return None
    return activity_crud.get_activity_by_id_if_is_public(activity_id, db)


def is_hidden_from(activity: activity_schema.ActivityRead, requester_user_id: int | None, *, hide_attr: str) -> bool:
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
