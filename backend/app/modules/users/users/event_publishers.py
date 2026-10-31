"""Publish the users domain events through the platform publish facade."""

from collections.abc import Callable

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.users.users.events as users_events


def publish_deletion_requested(user_id: int, db: Session, *, commit: Callable[[], None], source: str) -> None:
    """Publish ``users.deletion_requested`` so a durable worker erases the account.

    The event is the work, so it is staged in the transactional outbox on ``db`` and a staging
    failure propagates.

    Args:
        user_id: The user whose account to erase.
        db: The session to stage the event on.
        commit: Zero-arg commit callable that ends the caller's transaction.
        source: Who asked for the deletion, as recorded on the event.
    """
    payload = users_events.DeletionRequestedPayload(user_id=user_id)
    platform_publisher.publish_committing(
        users_events.USERS_DELETION_REQUESTED,
        payload.model_dump(),
        source=source,
        db=db,
        commit=commit,
        metadata={core_event_metadata.META_USER_ID: user_id},
        schema_version=payload.SCHEMA_VERSION,
    )
