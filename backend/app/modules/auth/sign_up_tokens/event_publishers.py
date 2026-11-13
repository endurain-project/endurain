"""Publish the sign-up domain events through the platform publish facade."""

import uuid

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.auth.sign_up_tokens.events as sign_up_tokens_events


def publish_sign_up_verification_requested(user_id: uuid.UUID, db: Session) -> None:
    """Stage ``auth.sign_up_verification_requested`` in the caller's transaction.

    Args:
        user_id: The user who must verify their email.
        db: The producer's DB session; the caller commits it.
    """
    payload = sign_up_tokens_events.SignUpUserPayload(user_id=user_id)
    platform_publisher.publish_on_commit(
        sign_up_tokens_events.SIGN_UP_VERIFICATION_REQUESTED,
        payload.model_dump(mode="json"),
        source="api:sign_up",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_admin_invitation_requested(user_id: uuid.UUID, db: Session) -> None:
    """Stage ``auth.admin_invitation_requested`` in the caller's transaction.

    Args:
        user_id: The user an administrator created without a password.
        db: The producer's DB session; the caller commits it.
    """
    payload = sign_up_tokens_events.SignUpUserPayload(user_id=user_id)
    platform_publisher.publish_on_commit(
        sign_up_tokens_events.ADMIN_INVITATION_REQUESTED,
        payload.model_dump(mode="json"),
        source="api:create_user",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_email_change_verification_requested(user_id: uuid.UUID, db: Session) -> None:
    """Stage ``auth.email_change_verification_requested`` in the caller's transaction.

    Args:
        user_id: The user whose pending email address must be verified.
        db: The producer's DB session, holding the uncommitted pending change.
    """
    payload = sign_up_tokens_events.SignUpUserPayload(user_id=user_id)
    platform_publisher.publish_on_commit(
        sign_up_tokens_events.EMAIL_CHANGE_VERIFICATION_REQUESTED,
        payload.model_dump(mode="json"),
        source="api:change_email",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_email_changed(user_id: uuid.UUID, token_id: str, db: Session) -> None:
    """Stage ``auth.email_changed`` in the caller's transaction.

    Args:
        user_id: The user whose email address changed.
        token_id: The confirmed token, which records the previous and the new address.
        db: The producer's DB session, holding the uncommitted change.
    """
    payload = sign_up_tokens_events.EmailChangedPayload(user_id=user_id, token_id=token_id)
    platform_publisher.publish_on_commit(
        sign_up_tokens_events.EMAIL_CHANGED,
        payload.model_dump(mode="json"),
        source="api:verify_email",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_sign_up_approval_requested(user_id: uuid.UUID, admin_user_id: uuid.UUID, db: Session) -> None:
    """Stage ``auth.sign_up_approval_requested`` for one admin in the caller's transaction.

    Args:
        user_id: The user who signed up and awaits approval.
        admin_user_id: The admin who receives the email.
        db: The producer's DB session (see :func:`publish_sign_up_verification_requested`).
    """
    payload = sign_up_tokens_events.SignUpApprovalRequestedPayload(user_id=user_id, admin_user_id=admin_user_id)
    platform_publisher.publish_on_commit(
        sign_up_tokens_events.SIGN_UP_APPROVAL_REQUESTED,
        payload.model_dump(mode="json"),
        source="api:verify_email",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_sign_up_approved(user_id: uuid.UUID, db: Session) -> None:
    """Stage ``auth.sign_up_approved`` in the caller's transaction.

    Args:
        user_id: The approved user.
        db: The producer's DB session, holding the uncommitted approval.
    """
    payload = sign_up_tokens_events.SignUpUserPayload(user_id=user_id)
    platform_publisher.publish_on_commit(
        sign_up_tokens_events.SIGN_UP_APPROVED,
        payload.model_dump(mode="json"),
        source="api:approve_user",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_sign_up_existing_account(user_id: uuid.UUID, db: Session) -> None:
    """Stage ``auth.sign_up_existing_account`` for the owner of a reused email address.

    Args:
        user_id: The existing user whose email address a sign-up used.
        db: The producer's DB session (see :func:`publish_sign_up_verification_requested`).
    """
    payload = sign_up_tokens_events.SignUpUserPayload(user_id=user_id)
    platform_publisher.publish_on_commit(
        sign_up_tokens_events.SIGN_UP_EXISTING_ACCOUNT,
        payload.model_dump(mode="json"),
        source="api:sign_up",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_email_change_requested(user_id: uuid.UUID, db: Session) -> None:
    """Stage ``auth.email_change_requested`` for the user whose email change was requested.

    The payload carries the user id only: the pending address and the cancel link are read when the notice is sent.

    Args:
        user_id: The user whose address a change was requested for.
        db: The producer's DB session (see :func:`publish_sign_up_verification_requested`).
    """
    payload = sign_up_tokens_events.SignUpUserPayload(user_id=user_id)
    platform_publisher.publish_on_commit(
        sign_up_tokens_events.EMAIL_CHANGE_REQUESTED,
        payload.model_dump(mode="json"),
        source="api:change_email",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_email_change_address_taken(user_id: uuid.UUID, db: Session) -> None:
    """Stage ``auth.email_change_address_taken`` for the holder of an address another account asked to move to.

    Args:
        user_id: The user who holds the address.
        db: The producer's DB session (see :func:`publish_sign_up_verification_requested`).
    """
    payload = sign_up_tokens_events.SignUpUserPayload(user_id=user_id)
    platform_publisher.publish_on_commit(
        sign_up_tokens_events.EMAIL_CHANGE_ADDRESS_TAKEN,
        payload.model_dump(mode="json"),
        source="api:change_email",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )
