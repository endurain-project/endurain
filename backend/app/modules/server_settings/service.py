"""Application logic for reading and editing server settings."""

import os
from datetime import timedelta

from sqlalchemy.orm import Session

import core.config as core_config
import core.etag as core_etag
import core.exceptions as core_exceptions
import core.geocoding as core_geocoding
import core.logger as core_logger
import core.network as core_network
import modules.server_settings.change_utils as server_settings_change_utils
import modules.server_settings.constants as server_settings_constants
import modules.server_settings.contracts as server_settings_contracts
import modules.server_settings.crud as server_settings_crud
import modules.server_settings.event_publishers as server_settings_publishers
import modules.server_settings.schema as server_settings_schema
import modules.server_settings.tile_service as server_settings_tile_service

logger = core_logger.get_logger(__name__)


def server_settings_env_managed() -> dict[str, str]:
    """Return the settings fields an environment variable currently sets.

    Geocoding is imported as a block, so while any geocoding variable is set all of its
    fields are env-managed, each named by its most specific variable. The session policy
    and retention variables each manage only their own field.

    Returns:
        Field name to environment variable name.
    """
    per_field_env_vars = server_settings_constants.SESSION_ENV_VARS | server_settings_constants.RETENTION_ENV_VARS
    managed = {field: name for field, name in per_field_env_vars.items() if env_var_is_set(name)}
    if any(env_var_is_set(name) for name in server_settings_constants.GEOCODING_ENV_VAR_NAMES):
        photon = core_config.settings.REVERSE_GEO_PROVIDER == core_geocoding.GeocodingService.PHOTON
        managed |= {
            field: server_settings_constants.GEOCODING_PHOTON_ENV_VARS.get(field, name) if photon else name
            for field, name in server_settings_constants.GEOCODING_ENV_VARS.items()
        }
    return managed


def _to_admin_read(
    server_settings: server_settings_schema.ServerSettingsRead,
) -> server_settings_schema.ServerSettingsAdminRead:
    """Build the admin response: the stored settings without the API keys.

    Args:
        server_settings: Settings as stored.

    Returns:
        The settings with a flag per API key saying whether one is stored, and the
        fields an environment variable sets.
    """
    return server_settings_schema.ServerSettingsAdminRead(
        **server_settings.model_dump(exclude=set(server_settings_constants.SECRET_FIELDS)),
        tileserver_api_key_set=bool(server_settings.tileserver_api_key),
        geocoding_api_key_set=bool(server_settings.geocoding_api_key),
        env_managed=server_settings_env_managed(),
    )


def get_server_settings(db: Session, *, for_update: bool = False) -> server_settings_schema.ServerSettingsRead:
    """Return the server settings as stored (the tile API key stays encrypted).

    Args:
        db: Database session.
        for_update: Lock the row until the transaction ends; for a read that decides a write.

    Returns:
        The server settings.

    Raises:
        ServiceUnavailableError: If the settings row does not exist. The row is
            created by the migrations, so its absence is a broken install, not a
            missing resource.
    """
    server_settings = server_settings_crud.get_server_settings(db, for_update=for_update)
    if server_settings is None:
        raise core_exceptions.ServiceUnavailableError("Server settings are not initialised.")
    return server_settings


def get_session_policy(db: Session) -> server_settings_contracts.SessionPolicy:
    """Return how long tokens and sessions live.

    Args:
        db: Database session.

    Returns:
        The session policy. The timeouts are enforced together, so both are None while
        they are disabled.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    settings = get_server_settings(db)
    timeouts_enabled = settings.session_idle_timeout_enabled
    return server_settings_contracts.SessionPolicy(
        access_token_ttl=timedelta(minutes=settings.access_token_expire_minutes),
        refresh_token_ttl=timedelta(days=settings.refresh_token_expire_days),
        idle_timeout=timedelta(hours=settings.session_idle_timeout_hours) if timeouts_enabled else None,
        absolute_timeout=timedelta(hours=settings.session_absolute_timeout_hours) if timeouts_enabled else None,
    )


def get_server_settings_for_public(db: Session) -> server_settings_schema.ServerSettingsReadPublic:
    """Return the subset of server settings that is safe to expose unauthenticated.

    Args:
        db: Database session.

    Returns:
        The public settings, with the configured SSO redirect schemes.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    server_settings = get_server_settings(db)
    public_fields = server_settings.model_dump(
        include=set(server_settings_schema.ServerSettingsReadPublic.model_fields)
    )
    return server_settings_schema.ServerSettingsReadPublic(
        **public_fields,
        allowed_redirect_schemes=sorted(core_config.settings.ALLOWED_REDIRECT_SCHEMES),
    )


def get_server_settings_for_admin(db: Session) -> server_settings_schema.ServerSettingsAdminRead:
    """Return the server settings for an admin to view, without the tile API key.

    Args:
        db: Database session.

    Returns:
        The server settings, with a flag saying whether a tile API key is stored.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    return _to_admin_read(get_server_settings(db))


def get_allowed_tile_domains(db: Session) -> list[str]:
    """Return the tile domains the CSP ``img-src`` directive allows.

    Args:
        db: Database session.

    Returns:
        The built-in provider domains plus the configured custom tile server's domain.
        Only the built-in ones when the settings row does not exist.
    """
    try:
        server_settings = get_server_settings(db)
    except core_exceptions.ServiceUnavailableError:
        logger.warning("Server settings row is missing; allowing only the built-in tile domains")
        return server_settings_constants.DEFAULT_ALLOWED_TILE_DOMAINS.copy()
    return server_settings_tile_service.allowed_tile_domains_for_url(server_settings.tileserver_url)


def _require_geocoding_key(
    attributes: server_settings_schema.ServerSettingsEdit,
    current: server_settings_schema.ServerSettingsRead,
) -> None:
    """Refuse geocode.maps.co without an API key.

    Args:
        attributes: The request body.
        current: The settings as stored.

    Raises:
        InvalidInputError: If the geocode.maps.co service has no API key.
    """
    if core_geocoding.GeocodingService(attributes.geocoding_service) != core_geocoding.GeocodingService.GEOCODE:
        return
    has_key = (
        attributes.geocoding_api_key
        if server_settings_constants.GEOCODING_API_KEY_FIELD in attributes.model_fields_set
        else current.geocoding_api_key
    )
    if not has_key:
        raise core_exceptions.InvalidInputError("geocode.maps.co needs an API key")


def _reject_unsafe_geocoding_host(attributes: server_settings_schema.ServerSettingsEdit) -> None:
    """Refuse a self-hosted geocoding host the server must not dial.

    Resolves DNS, so callers run it without holding the settings row lock.

    Args:
        attributes: The request body.

    Raises:
        InvalidInputError: If the host is one the server must not dial.
    """
    service = core_geocoding.GeocodingService(attributes.geocoding_service)
    if service == core_geocoding.GeocodingService.GEOCODE:
        return
    scheme = "https" if attributes.geocoding_use_https else "http"
    host = attributes.geocoding_host or core_geocoding.DEFAULT_HOSTS[service]
    reason = core_network.url_rejection_reason_bounded(f"{scheme}://{host}/reverse", purpose="reverse_geocoding")
    if reason is not None:
        logger.warning("Refused a geocoding host", extra=core_logger.context(reason=reason))
        raise core_exceptions.InvalidInputError(
            f"Geocoding host {reason}; add it to SSRF_ALLOWED_HOSTS for a self-hosted instance"
        )


def get_geocoding_config(db: Session) -> core_geocoding.GeocodingConfig | None:
    """Return the reverse-geocoding configuration, ready to use.

    Args:
        db: Database session.

    Returns:
        The configuration with the API key decrypted, or None when the settings row is missing.

    Raises:
        ServiceUnavailableError: When the stored API key cannot be decrypted.
    """
    row = server_settings_crud.get_server_settings(db)
    if row is None:
        logger.warning("Server settings are unavailable; geocoding is disabled")
        return None
    return core_geocoding.GeocodingConfig(
        service=core_geocoding.GeocodingService(row.geocoding_service),
        host=row.geocoding_host,
        use_https=row.geocoding_use_https,
        rate_limit=row.geocoding_rate_limit,
        api_key=server_settings_change_utils.decrypt_secret(
            row.geocoding_api_key, server_settings_constants.GEOCODING_API_KEY_LABEL
        ),
    )


def edit_server_settings(
    attributes: server_settings_schema.ServerSettingsEdit,
    db: Session,
    *,
    if_match: str,
) -> server_settings_schema.ServerSettingsAdminRead:
    """Persist settings and publish a tile-settings fact when the tile source changed.

    The checks that resolve DNS run before the settings row is locked, so a slow
    resolver never holds the lock. The row is then locked for the rest of the edit, so
    two concurrent saves apply one after the other, each compared against what the
    previous one stored. Only fields whose value differs from the stored one count as
    changed: a client that sends the whole record on every save does not trigger a
    tile-settings event, a thumbnail regeneration or a DNS lookup for settings it did
    not touch.

    Args:
        attributes: The settings to apply.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated settings, as an admin read returns them.

    Raises:
        InvalidInputError: If the tile server URL cannot be dialled safely.
        ConflictError: If a changed field is set by an environment variable.
        PreconditionFailedError: If the settings changed since the client read them.
        ServiceUnavailableError: If the settings row does not exist.
    """
    snapshot = get_server_settings(db)
    # End the read transaction: the network checks below must not pin a connection snapshot.
    db.rollback()
    core_etag.require_if_match(if_match, snapshot.version, "server settings")
    snapshot_changes = server_settings_change_utils.changed_fields(
        attributes, snapshot, server_settings_constants.SECRET_FIELDS
    )
    if "tileserver_url" in snapshot_changes:
        server_settings_tile_service.reject_unsafe_tileserver(attributes.tileserver_url)
    if snapshot_changes & server_settings_constants.GEOCODING_FIELDS:
        _reject_unsafe_geocoding_host(attributes)

    current = get_server_settings(db, for_update=True)
    core_etag.require_if_match(if_match, current.version, "server settings")
    changed_fields = server_settings_change_utils.changed_fields(
        attributes, current, server_settings_constants.SECRET_FIELDS
    )
    if not changed_fields:
        db.rollback()
        return _to_admin_read(current)

    server_settings_change_utils.refuse_env_managed(changed_fields, server_settings_env_managed())
    if changed_fields & server_settings_constants.GEOCODING_FIELDS:
        _require_geocoding_key(attributes, current)
    # An unchanged key keeps its stored token instead of being re-encrypted.
    stored_secrets = {
        field: server_settings_change_utils.encrypt_secret(getattr(attributes, field))
        if field in changed_fields
        else getattr(current, field)
        for field in server_settings_constants.SECRET_FIELDS
        if field in attributes.model_fields_set
    }
    attributes = attributes.model_copy(update=stored_secrets)

    updated = server_settings_crud.edit_server_settings(attributes, db)
    changed_map_fields = changed_fields & server_settings_constants.MAP_FIELDS
    if changed_map_fields:
        server_settings_publishers.publish_tile_settings_changed(
            changed_map_fields,
            db,
            commit=db.commit,
            regenerate_thumbnails=updated.tileserver_regenerate_thumbnails_on_change,
        )
    else:
        db.commit()
    logger.info("Server settings updated", extra=core_logger.context(changed_fields=sorted(changed_fields)))
    return _to_admin_read(updated)


def env_var_is_set(name: str) -> bool:
    """Return whether the operator explicitly set an environment variable.

    A default value does not count. A secret read through ``read_secret`` also counts
    when only its ``_FILE`` variant is set.

    Args:
        name: The environment variable name.

    Returns:
        True when the variable was provided in the environment or ``.env``.
    """
    if name in server_settings_constants.FILE_SECRET_ENV_VARS:
        return name in os.environ or f"{name}_FILE" in os.environ
    return name in core_config.settings.model_fields_set
