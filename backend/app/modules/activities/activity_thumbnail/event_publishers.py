"""Publish the activity-thumbnail domain events through the platform publish facade."""

from collections.abc import Callable

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import modules.activities.activity_thumbnail.events as activity_thumbnail_events


def publish_backfill_requested(db: Session, *, commit: Callable[[], None], event_id: str) -> None:
    """Publish ``activity_thumbnail.backfill_requested`` so a worker renders the missing thumbnails.

    Staged in the transactional outbox on ``db`` when durable jobs are on, then relayed into a retryable
    job; otherwise dispatched on the in-process bus after ``commit``. The outbox keeps one row per event id,
    so a request published again under the same id queues nothing more.

    Args:
        db: The session to stage the event on.
        commit: Zero-arg commit callable that ends the caller's transaction.
        event_id: The request's id.
    """
    payload = activity_thumbnail_events.ThumbnailBackfillRequestedPayload()
    platform_publisher.publish_committing(
        activity_thumbnail_events.THUMBNAIL_BACKFILL_REQUESTED,
        payload.model_dump(mode="json"),
        source="scheduler:thumbnail_backfill",
        db=db,
        commit=commit,
        schema_version=payload.SCHEMA_VERSION,
        event_id=event_id,
    )
