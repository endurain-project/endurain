"""The one authorization gate for reading an activity's child sub-resources.

Laps, sets, streams and workout steps are all "rows hanging off an activity", and
the question "may this caller read them?" has the same answer for all four: the
caller must be able to see the parent activity, and the parent's ``hide_*`` flag
guarding that particular child must not be set against a non-owner.

Each child CRUD used to answer that question itself, inline, immediately before
its ``SELECT`` — four copies of an access-control rule living in the persistence
layer, where a reviewer looking for "who may read this" would not think to look.
Hoisting it here does two things: the rule exists once (a fix cannot land in three
of the four places), and it moves out of ``crud`` so the child modules can follow
the same router -> service -> crud layering the activities core does.

Both gates answer a plain boolean rather than returning the activity: a caller
that receives the parent row is a caller that can accidentally serve fields from
it, and most child reads need nothing but permission. Streams are the exception —
their masking is per stream *type* rather than one flag — so they resolve the
parent and pass it to their own filter.
"""

from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity.crud as activities_crud
import modules.activities.activity.schema as activities_schema
import modules.followers.integration_service as followers_integration
import modules.server_settings.integration_service as server_settings_integration

logger = core_logger.get_logger(__name__)


def resolve_readable_parent(
    activity_id: int,
    requester_user_id: int,
    db: Session,
) -> activities_schema.Activity | None:
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
    return activities_crud.get_viewable_activity_by_id_for_user(activity_id, requester_user_id, db, followee_ids)


def resolve_public_parent(activity_id: int, db: Session) -> activities_schema.Activity | None:
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
    return activities_crud.get_activity_by_id_if_is_public(activity_id, db)


def may_read_child(activity_id: int, requester_user_id: int, db: Session, *, hide_attr: str) -> bool:
    """Return whether an authenticated caller may read one of an activity's child resources.

    Args:
        activity_id: The parent activity.
        requester_user_id: The authenticated caller.
        db: Database session.
        hide_attr: Name of the parent's boolean ``hide_*`` flag guarding this
            child resource (e.g. ``"hide_laps"``).

    Returns:
        True when the caller may see the parent activity **and** either owns it or
        the guarding flag is unset.
    """
    activity = resolve_readable_parent(activity_id, requester_user_id, db)
    if activity is None:
        logger.debug(
            "Child read denied: the activity is not visible to the caller",
            extra=core_logger.context(
                activity_id=activity_id, requester_user_id=requester_user_id, hide_attr=hide_attr
            ),
        )
        return False

    if requester_user_id != activity.user_id and getattr(activity, hide_attr):
        logger.debug(
            "Child read denied: the hide flag is set for a non-owner",
            extra=core_logger.context(
                activity_id=activity_id, requester_user_id=requester_user_id, hide_attr=hide_attr
            ),
        )
        return False

    return True


def may_read_public_child(activity_id: int, db: Session, *, hide_attr: str) -> bool:
    """Return whether an anonymous caller may read one of an activity's child resources.

    Args:
        activity_id: The parent activity.
        db: Database session.
        hide_attr: Name of the parent's boolean ``hide_*`` flag guarding this
            child resource.

    Returns:
        True when the activity is publicly shareable (server setting on,
        ``visibility == 0``, not hidden) and the guarding flag is unset.
    """
    if not server_settings_integration.public_shareable_links_enabled(db):
        return False
    return activities_crud.get_public_activity_for_child_read(activity_id, db, hide_attr=hide_attr) is not None
