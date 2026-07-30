"""Publish the followers domain events through the platform publish facade.

Thin domain layer co-locating the module's event publishers: each function knows
its channel and correlation metadata and delegates envelope assembly, ambient
request-id stamping and best-effort delivery to :mod:`infra.publisher`. The
follow service calls these instead of building events itself, so it stays
ignorant of the substrate and of who subscribes.
"""

from collections.abc import Callable

from sqlalchemy.orm import Session

import infra.events as platform_events
import infra.publisher as platform_publisher
import modules.followers.events as followers_events


def publish_follower_requested(
    requester_user_id: int,
    target_user_id: int,
    db: Session,
    commit: Callable[[], None],
) -> None:
    """Publish ``follower.requested`` after a follow-request row is created.

    Args:
        requester_user_id: The user who requested to follow.
        target_user_id: The user being followed (who is notified). Carried in the
            payload (the subscriber notifies them) and mirrored into the metadata
            for event-log correlation.
        db: The producer's DB session, used for durable outbox delivery when
            durable jobs are enabled for this event type.
        commit: Commit the relationship row and outbox event together.

    Returns:
        None.
    """
    platform_publisher.publish_committing(
        followers_events.FOLLOWER_REQUESTED,
        {"requester_user_id": requester_user_id, "target_user_id": target_user_id},
        source="api:create_follower",
        metadata={platform_events.META_USER_ID: target_user_id},
        db=db,
        commit=commit,
    )


def publish_follower_accepted(
    accepter_user_id: int,
    requester_user_id: int,
    db: Session,
    commit: Callable[[], None],
) -> None:
    """Publish ``follower.accepted`` after a pending request is accepted.

    Args:
        accepter_user_id: The user who accepted the request.
        requester_user_id: The original requester (who is notified). Carried in
            the payload and mirrored into the metadata for correlation.
        db: The producer's DB session (see :func:`publish_follower_requested`).
        commit: Commit the relationship row and outbox event together.

    Returns:
        None.
    """
    platform_publisher.publish_committing(
        followers_events.FOLLOWER_ACCEPTED,
        {"accepter_user_id": accepter_user_id, "requester_user_id": requester_user_id},
        source="api:accept_follower",
        metadata={platform_events.META_USER_ID: requester_user_id},
        db=db,
        commit=commit,
    )
