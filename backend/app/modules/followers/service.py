"""Application logic for follower relationships.

Currently hosts the privacy-aware read surface: whether a requester may view a
target user's follower / following graph. Access decisions live here (not only
in the router), per the module template. The write flows (follow / accept /
unfollow) and the pub/sub notifications move here in later FLW1 phases.

A user's follow graph is visible only to the user and their accepted followers.
Endurain has no public-profile concept: profiles are never public, and only
individual activities can be shared (via server-level public links), so no
"public" tier applies to the follow graph.
"""

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.followers.crud as followers_crud
import modules.followers.event_publishers as followers_event_publishers
import modules.followers.schema as followers_schema

logger = core_logger.get_logger(__name__)


def requester_may_view_network(target_user_id: int, requester_user_id: int, db: Session) -> bool:
    """Return whether the requester may view the target's follower/following graph.

    A user's social graph is visible only to the user themselves and to their
    **accepted** followers. There is no public-profile tier: profiles are never
    public in Endurain (only individual activities can be shared, via server-level
    public links). This closes the prior IDOR where any authenticated user could
    enumerate any user's followers.

    Args:
        target_user_id: The user whose network is being listed.
        requester_user_id: The authenticated user making the request.
        db: Database session.

    Returns:
        True if the requester is permitted to view the network.
    """
    if requester_user_id == target_user_id:
        return True

    relationship = followers_crud.get_follower_for_user_id_and_target_user_id(requester_user_id, target_user_id, db)
    return relationship is not None and relationship.status == followers_schema.FollowStatus.ACCEPTED


def _ensure_may_view_network(target_user_id: int, requester_user_id: int, db: Session) -> None:
    """Raise :class:`PermissionDeniedError` unless the requester may view the target's network."""
    if not requester_may_view_network(target_user_id, requester_user_id, db):
        logger.warning(
            "Denied access to a user's follower network",
            extra=core_logger.context(requester_user_id=requester_user_id, target_user_id=target_user_id),
        )
        raise core_exceptions.PermissionDeniedError("You do not have permission to view this user's followers")


def list_followers(
    target_user_id: int, requester_user_id: int, db: Session
) -> list[followers_schema.FollowRelationship]:
    """List the target's followers, enforcing profile privacy.

    Args:
        target_user_id: The user whose followers to list.
        requester_user_id: The authenticated requester.
        db: Database session.

    Returns:
        The target's follower records.

    Raises:
        PermissionDeniedError: When the requester may not view this network.
    """
    _ensure_may_view_network(target_user_id, requester_user_id, db)
    return followers_crud.get_all_followers_by_user_id(target_user_id, db)


def list_following(
    target_user_id: int, requester_user_id: int, db: Session
) -> list[followers_schema.FollowRelationship]:
    """List who the target follows, enforcing profile privacy.

    Args:
        target_user_id: The user whose following list to return.
        requester_user_id: The authenticated requester.
        db: Database session.

    Returns:
        The target's following records.

    Raises:
        PermissionDeniedError: When the requester may not view this network.
    """
    _ensure_may_view_network(target_user_id, requester_user_id, db)
    return followers_crud.get_all_following_by_user_id(target_user_id, db)


def count_followers(target_user_id: int, requester_user_id: int, db: Session, *, accepted_only: bool = False) -> int:
    """Count the target's followers, enforcing profile privacy.

    Args:
        target_user_id: The user whose followers to count.
        requester_user_id: The authenticated requester.
        db: Database session.
        accepted_only: Count only accepted followers when True.

    Returns:
        The number of follower records.

    Raises:
        PermissionDeniedError: When the requester may not view this network.
    """
    _ensure_may_view_network(target_user_id, requester_user_id, db)
    return followers_crud.count_followers_by_user_id(target_user_id, db, accepted_only=accepted_only)


def count_following(target_user_id: int, requester_user_id: int, db: Session, *, accepted_only: bool = False) -> int:
    """Count who the target follows, enforcing profile privacy.

    Args:
        target_user_id: The user whose following to count.
        requester_user_id: The authenticated requester.
        db: Database session.
        accepted_only: Count only accepted relationships when True.

    Returns:
        The number of following records.

    Raises:
        PermissionDeniedError: When the requester may not view this network.
    """
    _ensure_may_view_network(target_user_id, requester_user_id, db)
    return followers_crud.count_following_by_user_id(target_user_id, db, accepted_only=accepted_only)


def get_user_relationship(other_user_id: int, requester_user_id: int, db: Session) -> followers_schema.RelationshipView:
    """Return the authenticated user's relationship with another user (both directions).

    Only ever reports relationships the requester is part of — their outgoing
    follow of ``other_user_id`` and ``other_user_id``'s incoming follow of them —
    so there is no way to probe arbitrary pairs.

    Args:
        other_user_id: The other user in the relationship.
        requester_user_id: The authenticated requester.
        db: Database session.

    Returns:
        The requester's outgoing and incoming follow relationships with the other
        user (either may be None).
    """
    outgoing = followers_crud.get_follower_for_user_id_and_target_user_id(requester_user_id, other_user_id, db)
    incoming = followers_crud.get_follower_for_user_id_and_target_user_id(other_user_id, requester_user_id, db)
    return followers_schema.RelationshipView(outgoing=outgoing, incoming=incoming)


def follow_user(requester_user_id: int, target_user_id: int, db: Session) -> followers_schema.FollowRelationship:
    """Create a follow request and publish ``follower.requested``.

    The CRUD row write is the source of truth; the notification is produced by the
    ``follower.requested`` subscriber reacting to the published event, so the
    request succeeds even if notification delivery later fails.

    Args:
        requester_user_id: The authenticated user requesting to follow.
        target_user_id: The user to follow.
        db: Database session.

    Returns:
        The newly created follow relationship as a DTO.
    """
    follower = followers_crud.create_follower(requester_user_id, target_user_id, db)
    followers_event_publishers.publish_follower_requested(requester_user_id, target_user_id, db)
    logger.debug(
        "Follow requested",
        extra=core_logger.context(requester_user_id=requester_user_id, target_user_id=target_user_id),
    )
    return follower


def accept_follow_request(accepter_user_id: int, requester_user_id: int, db: Session) -> None:
    """Accept a pending follow request and publish ``follower.accepted``.

    Args:
        accepter_user_id: The authenticated user accepting the request.
        requester_user_id: The user whose pending request is being accepted.
        db: Database session.

    Returns:
        None.
    """
    followers_crud.accept_follower(accepter_user_id, requester_user_id, db)
    followers_event_publishers.publish_follower_accepted(accepter_user_id, requester_user_id, db)
    logger.debug(
        "Follow request accepted",
        extra=core_logger.context(accepter_user_id=accepter_user_id, requester_user_id=requester_user_id),
    )


def unfollow_user(requester_user_id: int, target_user_id: int, db: Session) -> None:
    """Stop following a user (the requester unfollows the target).

    Args:
        requester_user_id: The authenticated user who is unfollowing.
        target_user_id: The user being unfollowed.
        db: Database session.

    Returns:
        None.
    """
    followers_crud.delete_follower(requester_user_id, target_user_id, db)
    logger.debug(
        "Unfollowed a user",
        extra=core_logger.context(requester_user_id=requester_user_id, target_user_id=target_user_id),
    )


def remove_follower(user_id: int, follower_user_id: int, db: Session) -> None:
    """Remove one of the authenticated user's followers.

    Args:
        user_id: The authenticated user removing a follower.
        follower_user_id: The follower to remove.
        db: Database session.

    Returns:
        None.
    """
    followers_crud.delete_follower(follower_user_id, user_id, db)
    logger.debug(
        "Removed a follower",
        extra=core_logger.context(user_id=user_id, follower_user_id=follower_user_id),
    )


def list_accepted_followee_ids(user_id: int, db: Session) -> list[int]:
    """List the ids of users the given user follows (accepted only).

    The clean read interface the activities feed and visibility filter consume so
    the activities module never touches the followers table directly.

    Args:
        user_id: The follower whose accepted followees to list.
        db: Database session.

    Returns:
        The accepted followee user ids (empty list if none).
    """
    return followers_crud.list_accepted_followee_ids(user_id, db)
