"""Application logic for editing server settings."""

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import core.network as core_network
import modules.server_settings.crud as server_settings_crud
import modules.server_settings.event_publishers as server_settings_publishers
import modules.server_settings.schema as server_settings_schema

logger = core_logger.get_logger(__name__)

_MAP_FIELDS = frozenset({"tileserver_url", "tileserver_api_key", "map_background_color"})


def _reject_unsafe_tileserver(tile_url: str) -> None:
    """Refuse a tile URL that resolves somewhere the server must not dial.

    The renderer already refuses the request at tile-fetch time, but that is a
    background job: the admin who set the value sees no error, and the bad value
    is persisted meanwhile. Checking here answers the write instead, so a URL
    pointing at cloud metadata or an internal service never reaches the row.

    It lives in the service rather than in the schema validator because the check
    resolves DNS, and the schema is also what deserializes settings on every
    *read* — a validator would put a lookup on the read path of the whole app.

    Args:
        tile_url: The tile URL template being saved.

    Returns:
        None.

    Raises:
        InvalidInputError: When the template cannot be resolved to a URL, or the
            URL is not one the server may dial.
    """
    try:
        # The renderer resolves the template the same way before every fetch, so
        # a placeholder it cannot fill is a broken template, not a save-time
        # quirk — reported here rather than as a 500 from a background job.
        probe_url = tile_url.format(z=0, x=0, y=0)
    except (IndexError, KeyError) as err:
        raise core_exceptions.InvalidInputError(
            "Tile server URL contains a placeholder the renderer cannot fill"
        ) from err

    reason = core_network.url_rejection_reason(probe_url, purpose="activity_thumbnail_tile")
    if reason is None:
        return
    logger.warning(
        "Refused a tile server URL that targets a non-public address",
        extra=core_logger.context(reason=reason),
    )
    raise core_exceptions.InvalidInputError(f"Tile server {reason}")


def edit_server_settings(
    attributes: server_settings_schema.ServerSettingsEdit,
    db: Session,
) -> server_settings_schema.ServerSettingsRead:
    """Persist settings and publish a tile-settings fact when applicable."""
    changed_fields = set(attributes.model_dump(exclude_unset=True))
    if "tileserver_url" in changed_fields:
        _reject_unsafe_tileserver(attributes.tileserver_url)
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
