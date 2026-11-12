"""Publish the account-security domain events through the platform publish facade."""

import uuid

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.auth.account_security.events as account_security_events


def publish_account_security_changed(
    user_id: int,
    change: account_security_events.AccountSecurityChange,
    db: Session,
    *,
    idp_id: uuid.UUID | None = None,
    access_type: str | None = None,
) -> None:
    """Stage ``auth.account_security_changed`` in the caller's transaction.

    Args:
        user_id: The user whose account security changed.
        change: What changed.
        db: The producer's DB session; the event is published when it commits.
        idp_id: The identity provider concerned, for an unlink.
        access_type: The access type the user now has, for a role change.
    """
    payload = account_security_events.AccountSecurityChangedPayload(
        user_id=user_id, change=change, idp_id=idp_id, access_type=access_type
    )
    platform_publisher.publish_on_commit(
        account_security_events.ACCOUNT_SECURITY_CHANGED,
        payload.model_dump(mode="json"),
        source="api:account_security",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_step_up_session_ended(user_id: int, db: Session) -> None:
    """Stage ``auth.step_up_session_ended`` in the caller's transaction.

    Args:
        user_id: The user whose session the failed step-ups ended.
        db: The producer's DB session; the event is published when it commits.
    """
    payload = account_security_events.StepUpSessionEndedPayload(user_id=user_id)
    platform_publisher.publish_on_commit(
        account_security_events.STEP_UP_SESSION_ENDED,
        payload.model_dump(mode="json"),
        source="api:step_up",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_step_up_locked(user_id: int, db: Session) -> None:
    """Publish ``auth.step_up_locked`` for an account that failed step-ups locked.

    The lock is applied by a request that fails, so there is no transaction to stage the event in and it is
    published on its own. The notices it triggers are advisory: a lost event leaves the lock in place and audited.

    Args:
        user_id: The user whose step-up was locked.
        db: The producer's DB session.
    """
    payload = account_security_events.StepUpLockedPayload(user_id=user_id)
    platform_publisher.publish(
        account_security_events.STEP_UP_LOCKED,
        payload.model_dump(mode="json"),
        source="api:step_up",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )
