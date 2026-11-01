"""Publish the account-security domain events through the platform publish facade."""

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.auth.account_security.events as account_security_events


def publish_account_security_changed(
    user_id: int,
    change: account_security_events.AccountSecurityChange,
    db: Session,
    *,
    idp_id: int | None = None,
) -> None:
    """Stage ``auth.account_security_changed`` in the caller's transaction.

    Args:
        user_id: The user whose account security changed.
        change: What changed.
        db: The producer's DB session; the event is published when it commits.
        idp_id: The identity provider concerned, for an unlink.
    """
    payload = account_security_events.AccountSecurityChangedPayload(user_id=user_id, change=change, idp_id=idp_id)
    platform_publisher.publish_on_commit(
        account_security_events.ACCOUNT_SECURITY_CHANGED,
        payload.model_dump(mode="json"),
        source="api:account_security",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )
