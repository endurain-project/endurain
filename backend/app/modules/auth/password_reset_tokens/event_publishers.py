"""Publish the password reset domain events through the platform publish facade."""

import uuid

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.auth.password_reset_tokens.events as password_reset_tokens_events


def publish_password_reset_requested(
    user_id: uuid.UUID | None, ip_address: str | None, user_agent: str | None, db: Session
) -> None:
    """Stage ``auth.password_reset_requested`` in the caller's transaction.

    Args:
        user_id: The account registered for the requested address, or ``None`` when there is none.
        ip_address: The requester's client address.
        user_agent: The requester's ``User-Agent``.
        db: The producer's DB session; the caller commits it.
    """
    payload = password_reset_tokens_events.PasswordResetRequestedPayload(
        user_id=user_id, ip_address=ip_address, user_agent=user_agent
    )
    platform_publisher.publish_on_commit(
        password_reset_tokens_events.PASSWORD_RESET_REQUESTED,
        payload.model_dump(mode="json"),
        source="api:request_password_reset",
        metadata={} if user_id is None else {core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_password_reset_completed(user_id: uuid.UUID, db: Session) -> None:
    """Stage ``auth.password_reset_completed`` in the caller's transaction.

    Args:
        user_id: The user whose password was reset.
        db: The producer's DB session; the event is published when it commits.
    """
    payload = password_reset_tokens_events.PasswordResetCompletedPayload(user_id=user_id)
    platform_publisher.publish_on_commit(
        password_reset_tokens_events.PASSWORD_RESET_COMPLETED,
        payload.model_dump(mode="json"),
        source="api:confirm_password_reset",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )
