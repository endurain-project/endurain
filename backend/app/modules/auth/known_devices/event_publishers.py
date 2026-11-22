"""Publish the known-devices domain events through the platform publish facade."""

import uuid
from datetime import datetime

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.auth.known_devices.events as known_devices_events


def publish_new_device_sign_in(
    user_id: uuid.UUID,
    db: Session,
    *,
    browser: str,
    operating_system: str,
    device_type: str,
    ip_address: str,
    method: known_devices_events.SignInMethod,
    signed_in_at: datetime,
) -> None:
    """Stage ``auth.new_device_sign_in`` in the caller's transaction.

    Args:
        user_id: The user who signed in.
        db: The producer's DB session; the event is published when it commits.
        browser: The browser family the user agent names.
        operating_system: The operating-system family the user agent names.
        device_type: ``PC``, ``Mobile`` or ``Tablet``, from the user agent.
        ip_address: The client address of the sign-in.
        method: How the user signed in.
        signed_in_at: When the sign-in happened.
    """
    payload = known_devices_events.NewDeviceSignInPayload(
        user_id=user_id,
        browser=browser,
        operating_system=operating_system,
        device_type=device_type,
        ip_address=ip_address,
        method=method,
        signed_in_at=signed_in_at,
    )
    platform_publisher.publish_on_commit(
        known_devices_events.NEW_DEVICE_SIGN_IN,
        payload.model_dump(mode="json"),
        source="api:known_devices",
        metadata={core_event_metadata.META_USER_ID: str(user_id)},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )
