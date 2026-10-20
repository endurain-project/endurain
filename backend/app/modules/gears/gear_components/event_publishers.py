"""Publish the gear component domain events through the platform publish facade.

Each function knows its channel and correlation metadata and delegates envelope
assembly and delivery to :mod:`jasil.publisher`. They only stage: the caller commits,
and the event follows that commit, so a rolled-back write publishes nothing.
"""

from collections.abc import Iterable

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.gears.gear_components.events as gear_component_events


def publish_gear_component_created(gear_component_id: int, gear_id: int, user_id: int, db: Session) -> None:
    """Publish ``gear_component.created`` after a component row is staged.

    Args:
        gear_component_id: The created component's ID.
        gear_id: The gear it belongs to.
        user_id: The owning user's ID.
        db: The producer's DB session, used for durable outbox delivery.
    """
    payload = gear_component_events.GearComponentCreatedPayload(
        gear_component_id=gear_component_id, gear_id=gear_id, user_id=user_id
    )
    platform_publisher.publish_on_commit(
        gear_component_events.GEAR_COMPONENT_CREATED,
        payload.model_dump(),
        source="api:create_gear_component",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_gear_component_updated(
    gear_component_id: int, gear_id: int, user_id: int, db: Session, *, changed_fields: Iterable[str]
) -> None:
    """Publish ``gear_component.updated`` after a component's columns change.

    Args:
        gear_component_id: The updated component's ID.
        gear_id: The gear it belongs to.
        user_id: The owning user's ID.
        db: The producer's DB session, used for durable outbox delivery.
        changed_fields: The columns this update wrote; sorted before publishing so the
            order does not depend on the producer.
    """
    payload = gear_component_events.GearComponentUpdatedPayload(
        gear_component_id=gear_component_id,
        gear_id=gear_id,
        user_id=user_id,
        changed_fields=sorted(changed_fields),
    )
    platform_publisher.publish_on_commit(
        gear_component_events.GEAR_COMPONENT_UPDATED,
        payload.model_dump(),
        source="api:edit_gear_component",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_gear_component_deleted(gear_component_id: int, gear_id: int, user_id: int, db: Session) -> None:
    """Publish ``gear_component.deleted`` after a component row is staged for deletion.

    Args:
        gear_component_id: The removed component's ID.
        gear_id: The gear it belonged to.
        user_id: The owning user's ID.
        db: The producer's DB session, used for durable outbox delivery.
    """
    payload = gear_component_events.GearComponentDeletedPayload(
        gear_component_id=gear_component_id, gear_id=gear_id, user_id=user_id
    )
    platform_publisher.publish_on_commit(
        gear_component_events.GEAR_COMPONENT_DELETED,
        payload.model_dump(),
        source="api:delete_gear_component",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )
