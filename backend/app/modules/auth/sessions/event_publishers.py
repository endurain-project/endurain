"""Publish the sessions domain events through the platform publish facade."""

import uuid

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.auth.sessions.events as sessions_events


def publish_sessions_revoked(
    user_id: uuid.UUID,
    db: Session,
    *,
    session_id: str | None = None,
    except_session_id: str | None = None,
) -> None:
    """Stage ``auth.sessions_revoked`` in the caller's transaction.

    Args:
        user_id: The user whose sessions were revoked.
        db: The producer's DB session; the event is published when it commits.
        session_id: The one revoked session; None when every session of the user was revoked.
        except_session_id: With no ``session_id``, the one session of the user that was kept.
    """
    payload = sessions_events.SessionsRevokedPayload(
        user_id=user_id, session_id=session_id, except_session_id=except_session_id
    )
    platform_publisher.publish_on_commit(
        sessions_events.SESSIONS_REVOKED,
        payload.model_dump(mode="json"),
        source="api:sessions",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )
