"""Publish the gear domain events through the platform publish facade.

Each function knows its channel and correlation metadata and delegates envelope
assembly and delivery to :mod:`jasil.publisher`. They only stage: the caller commits,
and the event follows that commit, so a rolled-back write publishes nothing.
"""

from collections.abc import Iterable

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.gears.gear.events as gear_events


def publish_gear_created(gear_id: int, user_id: int, db: Session) -> None:
    """Publish ``gear.created`` after a gear row is staged.

    Args:
        gear_id: The created gear's ID.
        user_id: The owning user's ID.
        db: The producer's DB session, used for durable outbox delivery.
    """
    payload = gear_events.GearCreatedPayload(gear_id=gear_id, user_id=user_id)
    platform_publisher.publish_on_commit(
        gear_events.GEAR_CREATED,
        payload.model_dump(),
        source="api:create_gear",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_gear_updated(gear_id: int, user_id: int, db: Session, *, changed_fields: Iterable[str]) -> None:
    """Publish ``gear.updated`` after a gear's columns change.

    Args:
        gear_id: The updated gear's ID.
        user_id: The owning user's ID.
        db: The producer's DB session, used for durable outbox delivery.
        changed_fields: The columns this update wrote; sorted before publishing so the
            order does not depend on the producer.
    """
    payload = gear_events.GearUpdatedPayload(gear_id=gear_id, user_id=user_id, changed_fields=sorted(changed_fields))
    platform_publisher.publish_on_commit(
        gear_events.GEAR_UPDATED,
        payload.model_dump(),
        source="api:edit_gear",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_gear_deleted(gear_id: int, user_id: int, db: Session) -> None:
    """Publish ``gear.deleted`` after a gear row is staged for deletion.

    Args:
        gear_id: The removed gear's ID.
        user_id: The owning user's ID.
        db: The producer's DB session, used for durable outbox delivery.
    """
    payload = gear_events.GearDeletedPayload(gear_id=gear_id, user_id=user_id)
    platform_publisher.publish_on_commit(
        gear_events.GEAR_DELETED,
        payload.model_dump(),
        source="api:delete_gear",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )
