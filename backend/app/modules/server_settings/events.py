"""Domain events published by server settings."""

from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict, Field

TILE_SETTINGS_CHANGED = "server_settings.tile_settings_changed"


class TileSettingsChangedPayload(VersionedPayload):
    """Validated payload for a tile-server settings change."""

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    changed_fields: list[str] = Field(default_factory=list)
    regenerate_thumbnails: bool = False
