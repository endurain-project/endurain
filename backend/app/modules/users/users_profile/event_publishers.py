"""Publish the profile import's domain events through the platform publish facade."""

from collections.abc import Callable

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.events as profile_events


def publish_import_requested(user_id: int, staged_key: str, db: Session, *, commit: Callable[[], None]) -> None:
    """Publish ``users.profile_import_requested`` so a worker imports the staged archive.

    The event is the work, so a staging failure propagates.

    Args:
        user_id: The importing user.
        staged_key: Storage key of the staged archive.
        db: The session to stage the event on.
        commit: Zero-arg commit callable that ends the caller's transaction.
    """
    payload = profile_events.ProfileImportRequestedPayload(user_id=user_id, staged_key=staged_key)
    platform_publisher.publish_committing(
        profile_events.USERS_PROFILE_IMPORT_REQUESTED,
        payload.model_dump(),
        source=profile_constants.IMPORT_SOURCE_API,
        db=db,
        commit=commit,
        metadata={core_event_metadata.META_USER_ID: user_id},
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_export_requested(user_id: int, db: Session, *, commit: Callable[[], None]) -> None:
    """Publish ``users.profile_export_requested`` so a worker builds the export.

    The event is the work, so a staging failure propagates.

    Args:
        user_id: The exporting user.
        db: The session to stage the event on.
        commit: Zero-arg commit callable that ends the caller's transaction.
    """
    payload = profile_events.ProfileExportRequestedPayload(user_id=user_id)
    platform_publisher.publish_committing(
        profile_events.USERS_PROFILE_EXPORT_REQUESTED,
        payload.model_dump(),
        source=profile_constants.EXPORT_SOURCE_API,
        db=db,
        commit=commit,
        metadata={core_event_metadata.META_USER_ID: user_id},
        schema_version=payload.SCHEMA_VERSION,
    )
