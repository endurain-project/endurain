"""Publish the sign-up domain events through the platform publish facade."""

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.auth.sign_up_tokens.events as sign_up_tokens_events


def publish_sign_up_verification_requested(user_id: int, db: Session) -> None:
    """Publish ``auth.sign_up_verification_requested`` for a new user.

    Args:
        user_id: The user who must verify their email.
        db: The producer's DB session, used for durable outbox delivery when durable
            jobs are enabled.
    """
    payload = sign_up_tokens_events.SignUpUserPayload(user_id=user_id)
    platform_publisher.publish(
        sign_up_tokens_events.SIGN_UP_VERIFICATION_REQUESTED,
        payload.model_dump(),
        source="api:sign_up",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_sign_up_approval_requested(user_id: int, admin_user_id: int, db: Session) -> None:
    """Publish ``auth.sign_up_approval_requested`` for one admin.

    Args:
        user_id: The user who signed up and awaits approval.
        admin_user_id: The admin who receives the email.
        db: The producer's DB session (see :func:`publish_sign_up_verification_requested`).
    """
    payload = sign_up_tokens_events.SignUpApprovalRequestedPayload(user_id=user_id, admin_user_id=admin_user_id)
    platform_publisher.publish(
        sign_up_tokens_events.SIGN_UP_APPROVAL_REQUESTED,
        payload.model_dump(),
        source="api:verify_email",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_sign_up_approved(user_id: int, db: Session) -> None:
    """Publish ``auth.sign_up_approved`` for an approved user.

    Args:
        user_id: The approved user.
        db: The producer's DB session (see :func:`publish_sign_up_verification_requested`).
    """
    payload = sign_up_tokens_events.SignUpUserPayload(user_id=user_id)
    platform_publisher.publish(
        sign_up_tokens_events.SIGN_UP_APPROVED,
        payload.model_dump(),
        source="api:approve_user",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )
