"""The server-settings surface consumed by other modules.

A small, curated interface stated as the *questions callers actually ask* rather
than as "here is the settings row". Consumers previously reached for ``crud``
(the full settings ORM surface) or ``utils`` — and ``utils`` answers with an HTTP
404, which is meaningless to the durable job worker and to the persistence layer,
both of which called it.

Settings are one global row that the rest of the application only reads, so this
surface is all reads. Writes stay behind the module's admin routes.
"""

from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.logger as core_logger
import modules.server_settings.contracts as server_settings_contracts
import modules.server_settings.crud as server_settings_crud

logger = core_logger.get_logger(__name__)


def public_shareable_links_enabled(db: Session) -> bool:
    """
    Return whether the server allows unauthenticated shareable links.

    Args:
        db: Database session.

    Returns:
        True when the feature is enabled. Denies when the settings row is
        missing: a broken install must not widen access.

    Raises:
        None.
    """
    settings = server_settings_crud.get_server_settings(db)
    if settings is None:
        logger.warning("Server settings are unavailable; denying public shareable links")
        return False
    return bool(settings.public_shareable_links)


def get_tile_server_settings(db: Session) -> server_settings_contracts.TileServerSettings:
    """
    Return the configured map-tile source, with the API key decrypted.

    Args:
        db: Database session.

    Returns:
        The tile settings. Every field is None when the settings row is missing,
        leaving the caller to apply its own rendering defaults.

    Raises:
        None.
    """
    settings = server_settings_crud.get_server_settings(db)
    if settings is None:
        logger.warning("Server settings are unavailable; falling back to tile defaults")
        return server_settings_contracts.TileServerSettings()
    api_key = None
    if settings.tileserver_api_key:
        api_key = core_cryptography.decrypt_token_fernet(settings.tileserver_api_key)
    return server_settings_contracts.TileServerSettings(
        tile_url=settings.tileserver_url,
        background_color=settings.map_background_color,
        api_key=api_key,
    )
