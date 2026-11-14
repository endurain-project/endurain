"""Publish the gear package's domain events through the platform publish facade."""

import uuid
from collections.abc import Callable

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.gears.gear.events as gears_events


def publish_deletion_requested(
    gear_id: uuid.UUID, user_id: uuid.UUID, job_id: uuid.UUID, db: Session, *, commit: Callable[[], None]
) -> None:
    """Publish ``gears.deletion_requested`` so a durable worker deletes the gear.

    The event is the work, so it is staged in the transactional outbox on ``db`` and a staging failure
    propagates.

    Args:
        gear_id: The gear to delete.
        user_id: The gear's owner.
        job_id: The job the deletion records its state against.
        db: The session to stage the event on.
        commit: Zero-arg commit callable that ends the caller's transaction.
    """
    payload = gears_events.DeletionRequestedPayload(user_id=user_id, gear_id=gear_id, job_id=job_id)
    platform_publisher.publish_committing(
        gears_events.GEAR_DELETION_REQUESTED,
        payload.model_dump(mode="json"),
        source="api:delete_gear",
        db=db,
        commit=commit,
        metadata={core_event_metadata.META_USER_ID: str(user_id)},
        schema_version=payload.SCHEMA_VERSION,
    )
