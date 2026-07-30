"""Application logic for follower relationships.

The privacy-aware read surface (whether a requester may view a target's follower
/ following graph) and the follow / accept / unfollow writes. Access decisions
live here, not in the router, so the same rule applies however this module is
reached.

A user's follow graph is visible only to the user and their accepted followers.
Endurain has no public-profile concept: profiles are never public, and only
individual activities can be shared (via server-level public links), so no
"public" tier applies to the follow graph.

This is the module's *own* application layer. What other modules may consume
lives in :mod:`modules.followers.integration_service`.
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
    target_user_id: int,
    requester_user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = 25,
    accepted_only: bool = False,
) -> followers_schema.FollowRelationshipPage:
    """Return one page of the target's followers with the matching total.

    Args:
        target_user_id: The user whose followers to list.
        requester_user_id: The authenticated requester.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.
        accepted_only: Exclude pending follow requests when True.

    Returns:
        The page envelope. ``total`` counts every follower matching the same
        filter, not just this page.

    Raises:
        PermissionDeniedError: When the requester may not view this network.
    """
    # Checked once here so the page and its total share a single authorisation
    # decision rather than each re-deriving it.
    _ensure_may_view_network(target_user_id, requester_user_id, db)
    items = followers_crud.get_all_followers_by_user_id(
        target_user_id, db, page_number=page_number, num_records=num_records, accepted_only=accepted_only
    )
    total = followers_crud.count_followers_by_user_id(target_user_id, db, accepted_only=accepted_only)
    return followers_schema.FollowRelationshipPage.build(items, total, page_number, num_records)


def list_following(
    target_user_id: int,
    requester_user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = 25,
    accepted_only: bool = False,
) -> followers_schema.FollowRelationshipPage:
    """Return one page of who the target follows with the matching total.

    Args:
        target_user_id: The user whose following list to return.
        requester_user_id: The authenticated requester.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.
        accepted_only: Exclude pending follow requests when True.

    Returns:
        The page envelope. ``total`` counts every followee matching the same
        filter, not just this page.

    Raises:
        PermissionDeniedError: When the requester may not view this network.
    """
    _ensure_may_view_network(target_user_id, requester_user_id, db)
    items = followers_crud.get_all_following_by_user_id(
        target_user_id, db, page_number=page_number, num_records=num_records, accepted_only=accepted_only
    )
    total = followers_crud.count_following_by_user_id(target_user_id, db, accepted_only=accepted_only)
    return followers_schema.FollowRelationshipPage.build(items, total, page_number, num_records)


def list_pending_requests(
    requester_user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = 25,
) -> followers_schema.FollowRelationshipPage:
    """Return one page of follow requests awaiting the caller's decision.

    Always scoped to the caller: a pending request is private to the two parties,
    so there is no ``target_user_id`` to pass and therefore nothing to probe.

    Args:
        requester_user_id: The authenticated caller.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.

    Returns:
        The page envelope.
    """
    items = followers_crud.get_pending_requests_for_user_id(
        requester_user_id, db, page_number=page_number, num_records=num_records
    )
    total = followers_crud.count_pending_requests_for_user_id(requester_user_id, db)
    return followers_schema.FollowRelationshipPage.build(items, total, page_number, num_records)


def reject_follow_request(target_user_id: int, requester_user_id: int, db: Session) -> None:
    """Decline a pending follow request addressed to the caller.

    Distinct from :func:`remove_follower`, which severs an already-accepted
    relationship. Both delete the same row, but only one of them is a decision
    the requester never had granted.

    Args:
        target_user_id: The authenticated user declining the request.
        requester_user_id: The user whose pending request is declined.
        db: Database session.

    Returns:
        None.
    """
    followers_crud.delete_follower(requester_user_id, target_user_id, db)
    logger.debug(
        "Follow request rejected",
        extra=core_logger.context(target_user_id=target_user_id, requester_user_id=requester_user_id),
    )


def delete_relationship(followee_id: int, follower_id: int, caller_user_id: int, db: Session) -> None:
    """Delete a follow relationship on behalf of either party.

    One operation instead of separate unfollow/remove-follower endpoints: the
    row is the same and the direction is explicit in the arguments, so the only
    difference was which of the two parties asked. Splitting it meant two routes
    distinguished by a singular/plural path segment.

    Args:
        followee_id: The user being followed.
        follower_id: The user doing the following.
        caller_user_id: The authenticated caller, who must be one of the two.
        db: Database session.

    Returns:
        None.

    Raises:
        PermissionDeniedError: When the caller is not part of the relationship.
    """
    if caller_user_id not in (followee_id, follower_id):
        logger.warning(
            "Blocked an attempt to delete a follow relationship the caller is not part of",
            extra=core_logger.context(caller_user_id=caller_user_id, followee_id=followee_id, follower_id=follower_id),
        )
        raise core_exceptions.PermissionDeniedError()
    followers_crud.delete_follower(follower_id, followee_id, db)
    logger.debug(
        "Deleted a follow relationship",
        extra=core_logger.context(caller_user_id=caller_user_id, followee_id=followee_id, follower_id=follower_id),
    )


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
