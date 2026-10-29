"""Publish the identity-provider domain events through the platform publish facade."""

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.auth.identity_providers.events as idp_events


def publish_idp_token_refresh_requested(user_id: int, db: Session) -> None:
    """Stage ``auth.idp_token_refresh_requested`` in the caller's transaction.

    Args:
        user_id: The user whose identity-provider tokens are to be refreshed.
        db: The producer's DB session; the event is published when it commits.
    """
    payload = idp_events.IdpTokenRefreshPayload(user_id=user_id)
    platform_publisher.publish_on_commit(
        idp_events.IDP_TOKEN_REFRESH_REQUESTED,
        payload.model_dump(),
        source="api:refresh_token",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_idp_linked(user_id: int, idp_id: int, db: Session) -> None:
    """Stage ``auth.idp_linked`` in the caller's transaction.

    Args:
        user_id: The user whose account gained the link.
        idp_id: The identity provider that was linked.
        db: The producer's DB session; the event is published when it commits.
    """
    payload = idp_events.IdpLinkedPayload(user_id=user_id, idp_id=idp_id)
    platform_publisher.publish_on_commit(
        idp_events.IDP_LINKED,
        payload.model_dump(),
        source="api:idp_callback",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )
