"""Publish the followers domain events through the platform publish facade.

Thin domain layer co-locating the module's event publishers: each function knows
its channel and correlation metadata and delegates envelope assembly, ambient
request-id stamping and best-effort delivery to :mod:`jasil.publisher`. The
follow service calls these instead of building events itself, so it stays
ignorant of the substrate and of who subscribes.
"""

from collections.abc import Callable

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.followers.events as followers_events


def publish_follower_requested(
    requester_user_id: int,
    target_user_id: int,
    db: Session,
    *,
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
    """
    payload = followers_events.FollowerRequestedPayload(
        requester_user_id=requester_user_id,
        target_user_id=target_user_id,
    )
    platform_publisher.publish_committing(
        followers_events.FOLLOWER_REQUESTED,
        payload.model_dump(),
        source="api:follow_user",
        metadata={core_event_metadata.META_USER_ID: target_user_id},
        db=db,
        commit=commit,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_follower_accepted(
    accepter_user_id: int,
    requester_user_id: int,
    db: Session,
    *,
    commit: Callable[[], None],
) -> None:
    """Publish ``follower.accepted`` after a pending request is accepted.

    Args:
        accepter_user_id: The user who accepted the request.
        requester_user_id: The original requester (who is notified). Carried in
            the payload and mirrored into the metadata for correlation.
        db: The producer's DB session (see :func:`publish_follower_requested`).
        commit: Commit the relationship row and outbox event together.
    """
    payload = followers_events.FollowerAcceptedPayload(
        accepter_user_id=accepter_user_id,
        requester_user_id=requester_user_id,
    )
    platform_publisher.publish_committing(
        followers_events.FOLLOWER_ACCEPTED,
        payload.model_dump(),
        source="api:accept_follow_request",
        metadata={core_event_metadata.META_USER_ID: requester_user_id},
        db=db,
        commit=commit,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_follower_request_removed(
    requester_user_id: int,
    target_user_id: int,
    db: Session,
    *,
    commit: Callable[[], None],
    source: str,
) -> None:
    """Publish ``follower.request_removed`` after a pending request is deleted unaccepted.

    Args:
        requester_user_id: The user whose follow request was removed.
        target_user_id: The user the request was addressed to. Carried in the payload
            (the subscriber clears their notification) and mirrored into the metadata
            for correlation.
        db: The producer's DB session (see :func:`publish_follower_requested`).
        commit: Commit the deletion and outbox event together.
        source: Origin label: the route that removed the request.
    """
    payload = followers_events.FollowerRequestRemovedPayload(
        requester_user_id=requester_user_id,
        target_user_id=target_user_id,
    )
    platform_publisher.publish_committing(
        followers_events.FOLLOWER_REQUEST_REMOVED,
        payload.model_dump(),
        source=source,
        metadata={core_event_metadata.META_USER_ID: target_user_id},
        db=db,
        commit=commit,
        schema_version=payload.SCHEMA_VERSION,
    )
