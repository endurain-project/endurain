"""Publish the Garmin Connect domain events through the platform publish facade."""

from collections.abc import Callable
from datetime import date

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.garmin.constants as garmin_constants
import modules.garmin.events as garmin_events


def publish_sync_requested(
    user_id: int,
    kind: garmin_constants.SyncKind,
    start_date: date | None,
    end_date: date | None,
    db: Session,
    *,
    commit: Callable[[], None],
    source: str,
) -> None:
    """Publish ``garmin.sync_requested`` so a durable worker runs the sync.

    The event is the work, so it is staged in the transactional outbox on ``db`` and a
    staging failure propagates.

    Args:
        user_id: The user whose account to sync.
        kind: What to pull.
        start_date: First day of the range, for a health sync.
        end_date: Last day of the range, for a health sync.
        db: The session to stage the event on.
        commit: Zero-arg commit callable that ends the caller's transaction.
        source: Who asked for the sync, as recorded on the event.
    """
    payload = garmin_events.SyncRequestedPayload(user_id=user_id, kind=kind, start_date=start_date, end_date=end_date)
    platform_publisher.publish_committing(
        garmin_events.GARMIN_SYNC_REQUESTED,
        payload.model_dump(mode="json"),
        source=source,
        db=db,
        commit=commit,
        metadata={core_event_metadata.META_USER_ID: user_id},
        schema_version=payload.SCHEMA_VERSION,
    )
