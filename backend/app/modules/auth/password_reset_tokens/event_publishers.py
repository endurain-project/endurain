"""Publish the password reset domain events through the platform publish facade."""

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.auth.password_reset_tokens.events as password_reset_tokens_events


def publish_password_reset_requested(user_id: int, db: Session) -> None:
    """Stage ``auth.password_reset_requested`` in the caller's transaction.

    Args:
        user_id: The user who should receive the reset email.
        db: The producer's DB session; the caller commits it.
    """
    payload = password_reset_tokens_events.PasswordResetRequestedPayload(user_id=user_id)
    platform_publisher.publish_on_commit(
        password_reset_tokens_events.PASSWORD_RESET_REQUESTED,
        payload.model_dump(),
        source="api:request_password_reset",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )
