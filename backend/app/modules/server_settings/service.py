"""Application logic for editing server settings."""

from sqlalchemy.orm import Session

import modules.server_settings.crud as server_settings_crud
import modules.server_settings.event_publishers as server_settings_publishers
import modules.server_settings.schema as server_settings_schema

_MAP_FIELDS = frozenset({"tileserver_url", "tileserver_api_key", "map_background_color"})


def edit_server_settings(
    attributes: server_settings_schema.ServerSettingsEdit,
    db: Session,
) -> server_settings_schema.ServerSettingsRead:
    """Persist settings and publish a tile-settings fact when applicable."""
    changed_fields = set(attributes.model_dump(exclude_unset=True))
    updated = server_settings_crud.edit_server_settings(attributes, db, commit=False)
    changed_map_fields = changed_fields & _MAP_FIELDS
    if changed_map_fields:
        server_settings_publishers.publish_tile_settings_changed(
            changed_map_fields,
            updated.tileserver_regenerate_thumbnails_on_change,
            db,
            db.commit,
        )
    else:
        db.commit()
    return updated
