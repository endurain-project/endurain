"""Publish the authentication domain events through the platform publish facade."""

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

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
        payload.model_dump(),
        source="api:authenticate_api_key",
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )
