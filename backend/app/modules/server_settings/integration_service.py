"""The server-settings surface consumed by other modules.

A small, curated interface stated as the *questions callers actually ask* rather
than as "here is the settings row". Settings are one global row that the rest of
the application only reads, so this surface is reads. Writes stay behind the
module's admin routes, apart from one: ``import_deprecated_env_settings`` is the boot
import of deprecated environment variables and is a unit of work that commits.
"""

from sqlalchemy.orm import Session

import core.geocoding as core_geocoding
import core.logger as core_logger
import core.mail as core_mail
import modules.server_settings.contracts as server_settings_contracts
import modules.server_settings.crud as server_settings_crud
import modules.server_settings.schema as server_settings_schema
import modules.server_settings.service as server_settings_service

logger = core_logger.get_logger(__name__)


def get_server_settings(db: Session) -> server_settings_schema.ServerSettingsRead:
    """Return the server settings, without the API keys.

    Callers need the sign-up, login and password policy; the keys are not theirs to
    hold, so it is blanked rather than handed over encrypted.

    Args:
        db: Database session.

    Returns:
        The server settings.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    return server_settings_service.get_server_settings(db).model_copy(
        update={"tileserver_api_key": None, "geocoding_api_key": None}
    )


def get_allowed_tile_domains(db: Session) -> list[str]:
    """Return the tile domains the CSP ``img-src`` directive allows.

    Args:
        db: Database session.

    Returns:
        The built-in provider domains plus the configured custom tile server's
        domain; only the built-in ones when the settings row is missing.
    """
    return server_settings_service.get_allowed_tile_domains(db)


def public_shareable_links_enabled(db: Session) -> bool:
    """Return whether the server allows unauthenticated shareable links.

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
    """Return the configured map-tile source, with the API key decrypted.

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
    api_key = server_settings_service.decrypt_tileserver_api_key(settings.tileserver_api_key)
    return server_settings_contracts.TileServerSettings(
        tile_url=settings.tileserver_url,
        background_color=settings.map_background_color,
        api_key=api_key,
    )


def get_mail_config(db: Session) -> core_mail.MailConfig | None:
    """Return the configured mail server, with the password decrypted.

    Args:
        db: Database session.

    Returns:
        The mail configuration, or None when mail is disabled.

    Raises:
        ServiceUnavailableError: When the stored password cannot be decrypted.
    """
    return server_settings_service.get_mail_config(db)


def is_mail_configured(db: Session) -> bool:
    """Return whether a mail server is configured, cheap enough for unauthenticated routes.

    Args:
        db: Database session.

    Returns:
        True when a mail host is stored. The settings were validated when saved.
    """
    return server_settings_service.is_mail_configured(db)


def get_geocoding_config(db: Session) -> core_geocoding.GeocodingConfig | None:
    """Return the configured reverse-geocoding service, with the API key decrypted.

    Args:
        db: Database session.

    Returns:
        The geocoding configuration, or None when the settings row is missing.

    Raises:
        ServiceUnavailableError: When the stored API key cannot be decrypted.
    """
    return server_settings_service.get_geocoding_config(db)


def get_session_policy(db: Session) -> server_settings_contracts.SessionPolicy:
    """Return how long tokens and sessions live.

    Args:
        db: Database session.

    Returns:
        The session policy; both timeouts are None while timeouts are disabled.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    return server_settings_service.get_session_policy(db)


def get_read_notification_retention_days(db: Session) -> int:
    """Return the age in days after which read notifications are purged.

    Args:
        db: Database session.

    Returns:
        The retention in days; 0 disables pruning.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    return server_settings_service.get_server_settings(db).read_notification_retention_days


def import_deprecated_env_settings(db: Session) -> None:
    """Save the deprecated environment variables into the database and warn about them.

    Called once at API startup, after the migrations. Commits.

    Args:
        db: Database session.

    Raises:
        ServiceUnavailableError: If a settings row does not exist.
    """
    server_settings_service.import_deprecated_env_settings(db)
