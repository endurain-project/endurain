"""Saving the deprecated environment variables into the database at startup."""

from sqlalchemy.orm import Session

import core.config as core_config
import core.geocoding as core_geocoding
import core.logger as core_logger
import core.mail as core_mail
import modules.server_settings.change_utils as server_settings_change_utils
import modules.server_settings.constants as server_settings_constants
import modules.server_settings.crud as server_settings_crud
import modules.server_settings.mail_service as server_settings_mail_service
import modules.server_settings.schema as server_settings_schema
import modules.server_settings.service as server_settings_service

logger = core_logger.get_logger(__name__)


def _import_mail_env(db: Session) -> list[str]:
    """Save the deprecated ``SMTP_*`` variables into the mail settings.

    Runs only when ``SMTP_HOST`` is set. Invalid values leave the stored settings
    unchanged and are logged, so a bad variable disables nothing and stops nothing,
    as before. Writes only the fields that differ; the caller commits.

    Args:
        db: Database session.

    Returns:
        The names of the ``SMTP_*`` variables that are set; empty when mail is not
        configured through the environment.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    if not server_settings_service.env_var_is_set(server_settings_constants.MAIL_ENV_VARS["host"]):
        return []
    settings = core_config.settings
    names = [name for name in server_settings_constants.SMTP_ENV_VARS if server_settings_service.env_var_is_set(name)]
    password = core_config.read_secret("SMTP_PASSWORD")
    if not settings.SMTP_SECURE:
        security = core_mail.MailSecurity.NONE
    elif settings.SMTP_SECURE_TYPE == "ssl":
        security = core_mail.MailSecurity.SSL
    else:
        security = core_mail.MailSecurity.STARTTLS

    problems = core_mail.mail_problems(
        server_settings_mail_service.build_mail_config(
            settings.SMTP_HOST or "",
            settings.SMTP_PORT,
            security.value,
            settings.SMTP_FROM,
            settings.SMTP_USERNAME,
            password,
        )
    )
    if problems:
        logger.error(
            "The SMTP environment variables are invalid, so the stored mail settings were left unchanged: "
            + "; ".join(problems),
            extra=core_logger.context(console=True),
        )
        return names

    current = server_settings_mail_service.read_mail_settings(db, for_update=True)
    target = {
        "host": settings.SMTP_HOST,
        "port": settings.SMTP_PORT,
        "security": security.value,
        "username": settings.SMTP_USERNAME,
        "from_address": settings.SMTP_FROM,
    }
    changes = server_settings_change_utils.differing(current, target)
    if server_settings_change_utils.secret_changed(
        current.password, password, server_settings_constants.MAIL_CREDENTIAL_LABEL
    ):
        changes[server_settings_constants.MAIL_CREDENTIAL_FIELD] = server_settings_change_utils.encrypt_secret(password)
    if changes:
        # Only the differing fields are written; the values were validated above.
        server_settings_crud.edit_mail_settings(server_settings_schema.MailSettingsEdit.model_construct(**changes), db)
        logger.info(
            "Mail settings imported from the environment", extra=core_logger.context(changed_fields=sorted(changes))
        )
    return names


def _import_geocoding_env(db: Session) -> list[str]:
    """Save the deprecated reverse-geocoding variables into the server settings.

    Runs only when at least one of them is set. An unknown provider leaves the stored
    settings unchanged and is logged, as it used to disable geocoding without stopping
    the application. Writes only the fields that differ; the caller commits.

    Args:
        db: Database session.

    Returns:
        The names of the geocoding variables that are set; empty when none is.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    names = [
        name
        for name in server_settings_constants.GEOCODING_ENV_VAR_NAMES
        if server_settings_service.env_var_is_set(name)
    ]
    if not names:
        return []
    settings = core_config.settings
    try:
        service = core_geocoding.GeocodingService(settings.REVERSE_GEO_PROVIDER)
    except ValueError:
        logger.error(
            "REVERSE_GEO_PROVIDER is not nominatim, photon or geocode, so the stored geocoding settings were left "
            "unchanged",
            extra=core_logger.context(console=True),
        )
        return names

    if service == core_geocoding.GeocodingService.GEOCODE:
        host, use_https = None, True
    else:
        prefix = service.name
        host_var, https_var = f"{prefix}_API_HOST", f"{prefix}_API_USE_HTTPS"
        # An unset host variable means the service's default host, not the default the settings carry.
        host = getattr(settings, host_var) if server_settings_service.env_var_is_set(host_var) else None
        use_https = getattr(settings, https_var)
        try:
            host = server_settings_schema.ServerSettingsGeocoding.validate_geocoding_host(host)
        except ValueError:
            logger.error(
                "The geocoding host variable is not a hostname or IP address with an optional port, so the stored "
                "geocoding settings were left unchanged",
                extra=core_logger.context(console=True),
            )
            return names
    api_key = None if settings.GEOCODES_MAPS_API == "changeme" else settings.GEOCODES_MAPS_API

    current = server_settings_service.get_server_settings(db, for_update=True)
    target = {
        "geocoding_service": service.value,
        "geocoding_host": host,
        "geocoding_use_https": use_https,
        "geocoding_rate_limit": settings.REVERSE_GEO_RATE_LIMIT,
    }
    changes = server_settings_change_utils.differing(current, target)
    if server_settings_change_utils.secret_changed(
        current.geocoding_api_key, api_key, server_settings_constants.GEOCODING_API_KEY_LABEL
    ):
        changes[server_settings_constants.GEOCODING_API_KEY_FIELD] = server_settings_change_utils.encrypt_secret(
            api_key
        )
    if changes:
        # Only the differing fields are written; the values were validated above.
        server_settings_crud.edit_server_settings(
            server_settings_schema.ServerSettingsEdit.model_construct(**changes), db
        )
        logger.info(
            "Geocoding settings imported from the environment",
            extra=core_logger.context(changed_fields=sorted(changes)),
        )
    return names


def _import_session_env(db: Session) -> list[str]:
    """Save the deprecated session and token policy variables into the server settings.

    Each set variable is imported on its own, and only when it differs. Writes only the
    fields that differ; the caller commits.

    Args:
        db: Database session.

    Returns:
        The names of the session policy variables that are set.

    Raises:
        ValueError: If the resulting absolute session timeout is shorter than the idle
            timeout. This is a configuration error that stops the start rather than
            silently weakening the policy.
        ServiceUnavailableError: If the settings row does not exist.
    """
    names = [
        name
        for name in server_settings_constants.SESSION_ENV_VARS.values()
        if server_settings_service.env_var_is_set(name)
    ]
    if not names:
        return []
    settings = core_config.settings
    current = server_settings_service.get_server_settings(db, for_update=True)
    targets = {
        field: getattr(settings, name)
        for field, name in server_settings_constants.SESSION_ENV_VARS.items()
        if name in names
    }
    changes = server_settings_change_utils.differing(current, targets)
    idle = changes.get("session_idle_timeout_hours", current.session_idle_timeout_hours)
    absolute = changes.get("session_absolute_timeout_hours", current.session_absolute_timeout_hours)
    if absolute < idle:
        raise ValueError(
            "SESSION_ABSOLUTE_TIMEOUT_HOURS and SESSION_IDLE_TIMEOUT_HOURS are inconsistent: "
            "the absolute timeout cannot be shorter than the idle timeout"
        )
    if changes:
        # Only the differing fields are written; the values were validated by the settings model.
        server_settings_crud.edit_server_settings(
            server_settings_schema.ServerSettingsEdit.model_construct(**changes), db
        )
        logger.info(
            "Session policy imported from the environment",
            extra=core_logger.context(changed_fields=sorted(changes)),
        )
    return names


def _import_retention_env(db: Session) -> list[str]:
    """Save the deprecated read-notification retention variable into the server settings.

    Writes only when the value differs; the caller commits.

    Args:
        db: Database session.

    Returns:
        The names of the retention variables that are set.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    names = [
        name
        for name in server_settings_constants.RETENTION_ENV_VARS.values()
        if server_settings_service.env_var_is_set(name)
    ]
    if not names:
        return []
    current = server_settings_service.get_server_settings(db, for_update=True)
    days = core_config.settings.READ_NOTIFICATION_RETENTION_DAYS
    if current.read_notification_retention_days != days:
        # The value was validated by the settings model.
        server_settings_crud.edit_server_settings(
            server_settings_schema.ServerSettingsEdit.model_construct(read_notification_retention_days=days), db
        )
        logger.info(
            "Read-notification retention imported from the environment",
            extra=core_logger.context(changed_fields=["read_notification_retention_days"]),
        )
    return names


def import_deprecated_env_settings(db: Session) -> None:
    """Save the deprecated environment variables into the database, once per start.

    A variable that is set overwrites the stored value only when it differs, and
    makes its field env-managed. One warning names every variable found. This is a
    unit of work: it commits.

    Args:
        db: Database session.

    Raises:
        ServiceUnavailableError: If a settings row does not exist.
    """
    deprecated_names = [
        *_import_mail_env(db),
        *_import_geocoding_env(db),
        *_import_session_env(db),
        *_import_retention_env(db),
    ]
    db.commit()
    if deprecated_names:
        logger.warning(
            server_settings_constants.DEPRECATED_ENV_WARNING.format(names=", ".join(deprecated_names)),
            extra=core_logger.context(console=True),
        )
