"""Publish the authentication domain events through the platform publish facade."""

import uuid

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.auth.authentication.events as authentication_events


def publish_api_key_used(api_key_id: str, db: Session) -> None:
    """Publish ``auth.api_key_used`` for a key that authenticated a request.

    The stamp it triggers is advisory: the subscriber is best-effort and has no durable handler, so a lost event is
    recovered by the next request with the key.

    Args:
        api_key_id: The key that authenticated the request.
        db: The producer's DB session.
    """
    payload = authentication_events.ApiKeyUsedPayload(api_key_id=api_key_id)
    platform_publisher.publish(
        authentication_events.API_KEY_USED,
        payload.model_dump(mode="json"),
        source="api:authenticate_api_key",
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_account_locked(user_id: uuid.UUID, db: Session) -> None:
    """Publish ``auth.account_locked`` for an account that failed sign-ins locked.

    The lock is applied by a request that fails, so there is no transaction to stage the event in and it is
    published on its own. The notices it triggers are advisory: a lost event leaves the lock in place and audited.

    Args:
        user_id: The user whose account was locked.
        db: The producer's DB session.
    """
    payload = authentication_events.AccountLockedPayload(user_id=user_id)
    platform_publisher.publish(
        authentication_events.ACCOUNT_LOCKED,
        payload.model_dump(mode="json"),
        source="api:login",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_mfa_locked(user_id: uuid.UUID, db: Session) -> None:
    """Publish ``auth.mfa_locked`` for an account that wrong MFA codes locked.

    The lock is applied by a request that fails, so there is no transaction to stage the event in and it is
    published on its own. The notices it triggers are advisory: a lost event leaves the lock in place and audited.

    Args:
        user_id: The user whose MFA sign-in was locked.
        db: The producer's DB session.
    """
    payload = authentication_events.MfaLockedPayload(user_id=user_id)
    platform_publisher.publish(
        authentication_events.MFA_LOCKED,
        payload.model_dump(mode="json"),
        source="api:mfa_verify",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_refresh_reuse_detected(user_id: uuid.UUID, db: Session) -> None:
    """Stage ``auth.refresh_reuse_detected`` in the caller's transaction.

    Args:
        user_id: The user whose session was ended by a reused refresh token.
        db: The producer's DB session; the event is published when it commits.
    """
    payload = authentication_events.RefreshReuseDetectedPayload(user_id=user_id)
    platform_publisher.publish_on_commit(
        authentication_events.REFRESH_REUSE_DETECTED,
        payload.model_dump(mode="json"),
        source="api:refresh",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )
