"""Publish server-settings domain events."""

from collections.abc import Callable, Iterable

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import modules.server_settings.events as server_settings_events


def publish_tile_settings_changed(
    changed_fields: Iterable[str],
    db: Session,
    *,
    commit: Callable[[], None],
    regenerate_thumbnails: bool,
) -> None:
    """Publish ``server_settings.tile_settings_changed`` after the tile source changed.

    Args:
        changed_fields: The tile-related settings fields that were written.
        db: The producer's DB session, used for durable outbox delivery.
        commit: Commit the settings row and outbox event together.
        regenerate_thumbnails: Whether subscribers should regenerate activity thumbnails.
    """
    payload = server_settings_events.TileSettingsChangedPayload(
        changed_fields=sorted(changed_fields),
        regenerate_thumbnails=regenerate_thumbnails,
    )
    platform_publisher.publish_committing(
        server_settings_events.TILE_SETTINGS_CHANGED,
        payload.model_dump(),
        source="api:edit_server_settings",
        db=db,
        commit=commit,
        schema_version=payload.SCHEMA_VERSION,
    )
