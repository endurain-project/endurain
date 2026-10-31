"""Publish the Strava domain events through the platform publish facade."""

from collections.abc import Callable

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.strava.constants as strava_constants
import modules.strava.events as strava_events


def publish_sync_requested(
    user_id: int,
    kind: strava_constants.SyncKind,
    db: Session,
    *,
    commit: Callable[[], None],
    source: str,
) -> None:
    """Publish ``strava.sync_requested`` so a durable worker runs the sync.

    The event is the work, so it is staged in the transactional outbox on ``db`` and a
    staging failure propagates.

    Args:
        user_id: The user whose account to sync.
        kind: What to do.
        db: The session to stage the event on.
        commit: Zero-arg commit callable that ends the caller's transaction.
        source: Who asked for the sync, as recorded on the event.
    """
    payload = strava_events.SyncRequestedPayload(user_id=user_id, kind=kind)
    platform_publisher.publish_committing(
        strava_events.STRAVA_SYNC_REQUESTED,
        payload.model_dump(mode="json"),
        source=source,
        db=db,
        commit=commit,
        metadata={core_event_metadata.META_USER_ID: user_id},
        schema_version=payload.SCHEMA_VERSION,
    )
