"""Application logic for reading and editing server settings."""

from pathlib import Path
from urllib.parse import urlparse

import jasil.providers as platform_providers
from fastapi import UploadFile
from sqlalchemy.orm import Session

import core.config as core_config
import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.i18n as core_i18n
import core.logger as core_logger
import core.mail as core_mail
import core.network as core_network
import modules.server_settings.constants as server_settings_constants
import modules.server_settings.crud as server_settings_crud
import modules.server_settings.email_messages as server_settings_email_messages
import modules.server_settings.event_publishers as server_settings_publishers
import modules.server_settings.schema as server_settings_schema
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)

_MAP_FIELDS = frozenset({"tileserver_url", "tileserver_api_key", "map_background_color"})
_LOGIN_PHOTO_FILENAME = "login.png"


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


def get_server_settings(db: Session) -> server_settings_schema.ServerSettingsRead:
    """Return the server settings as stored (the tile API key stays encrypted).

    Args:
        db: Database session.

    Returns:
        The server settings.

    Raises:
        NotFoundError: If the settings row does not exist.
    """
    server_settings = server_settings_crud.get_server_settings(db)
    if server_settings is None:
        raise core_exceptions.NotFoundError("Server settings not found")
    return server_settings


def get_server_settings_for_public(db: Session) -> server_settings_schema.ServerSettingsReadPublic:
    """Return the subset of server settings that is safe to expose unauthenticated.

    Args:
        db: Database session.

    Returns:
        The public settings, with the configured SSO redirect schemes.

    Raises:
        NotFoundError: If the settings row does not exist.
    """
    server_settings = get_server_settings(db)
    public_fields = server_settings.model_dump(
        include=set(server_settings_schema.ServerSettingsReadPublic.model_fields)
    )
    return server_settings_schema.ServerSettingsReadPublic(
        **public_fields,
        allowed_redirect_schemes=sorted(core_config.settings.ALLOWED_REDIRECT_SCHEMES),
    )


def get_server_settings_for_admin(db: Session) -> server_settings_schema.ServerSettingsRead:
    """Return the server settings with the tile API key decrypted, for an admin to view.

    Args:
        db: Database session.

    Returns:
        The server settings with a decrypted tile API key.

    Raises:
        NotFoundError: If the settings row does not exist.
    """
    server_settings = get_server_settings(db)
    decrypted_api_key = None
    if server_settings.tileserver_api_key:
        decrypted_api_key = core_cryptography.decrypt_token_fernet(server_settings.tileserver_api_key)
    return server_settings.model_copy(update={"tileserver_api_key": decrypted_api_key})


def get_tile_maps_templates() -> list[server_settings_schema.TileMapsTemplate]:
    """Return the built-in tile map templates an admin can pick from.

    Returns:
        One template per built-in tile provider.
    """
    return [
        server_settings_schema.TileMapsTemplate(template_id=template_id, **template_data)
        for template_id, template_data in server_settings_constants.TILE_MAPS_TEMPLATES.items()
    ]


def extract_domain_from_tile_url(url: str) -> str | None:
    """Extract the domain from a tile server URL for the CSP ``img-src`` directive.

    Args:
        url: Tile server URL template (e.g., https://tiles.example.com/map/{z}/{x}/{y}.png).

    Returns:
        The domain with protocol and wildcard, or None if the URL is invalid. For
        example ``https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png`` gives
        ``https://*.openstreetmap.org``; a localhost URL is returned as ``scheme://host``.
    """
    try:
        # {s} is Leaflet's subdomain placeholder (a, b, c), still used by some custom providers
        clean_url = url.replace("{s}", "a").replace("{S}", "a")

        parsed = urlparse(clean_url)
        if not parsed.scheme or not parsed.netloc:
            return None

        if parsed.netloc.startswith("localhost") or parsed.netloc.startswith("127."):
            return f"{parsed.scheme}://{parsed.netloc}"

        # Last two labels are the base domain (handles .com, .org, .co.uk, etc.)
        hostname = parsed.hostname or parsed.netloc
        parts = hostname.split(".")
        if len(parts) >= 2:
            return f"{parsed.scheme}://*.{'.'.join(parts[-2:])}"

        return f"{parsed.scheme}://*.{hostname}"
    except Exception:
        return None


def get_allowed_tile_domains(db: Session) -> list[str]:
    """Return the tile domains the CSP ``img-src`` directive allows.

    Args:
        db: Database session.

    Returns:
        The built-in provider domains plus the configured custom tile server's domain.
        Only the built-in ones when the settings cannot be read.
    """
    allowed_domains: list[str] = server_settings_schema.DEFAULT_ALLOWED_TILE_DOMAINS.copy()

    try:
        server_settings = get_server_settings(db)
        if server_settings.tileserver_url:
            custom_domain = extract_domain_from_tile_url(server_settings.tileserver_url)
            if custom_domain and custom_domain not in allowed_domains:
                allowed_domains.append(custom_domain)
    except Exception:
        logger.debug("Server settings unavailable for allowed tile domains; using defaults")

    return allowed_domains


def edit_server_settings(
    attributes: server_settings_schema.ServerSettingsEdit,
    db: Session,
) -> server_settings_schema.ServerSettingsRead:
    """Persist settings and publish a tile-settings fact when applicable.

    Args:
        attributes: The settings to apply; only the ones that were set are written.
        db: Database session.

    Returns:
        The updated settings as stored.

    Raises:
        InvalidInputError: If the tile server URL cannot be dialled safely.
        NotFoundError: If the settings row does not exist.
    """
    changed_fields = set(attributes.model_dump(exclude_unset=True))
    if "tileserver_url" in changed_fields:
        _reject_unsafe_tileserver(attributes.tileserver_url)
    if attributes.tileserver_api_key is not None:
        attributes = attributes.model_copy(
            update={"tileserver_api_key": core_cryptography.encrypt_token_fernet(attributes.tileserver_api_key)}
        )
    updated = server_settings_crud.edit_server_settings(attributes, db)
    changed_map_fields = changed_fields & _MAP_FIELDS
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
    return updated


def upload_login_photo(file: UploadFile, db: Session) -> None:
    """Save the custom login page photo and mark it as set.

    Args:
        file: The uploaded image.
        db: Database session.

    Raises:
        DomainError: If the upload fails validation or cannot be saved.
        NotFoundError: If the settings row does not exist.
    """
    core_file_uploads.save_validated_upload_sync(
        file,
        kind=core_file_uploads.UploadKind.IMAGE,
        upload_dir=core_config.SERVER_IMAGES_DIR,
        filename=_LOGIN_PHOTO_FILENAME,
    )
    server_settings_crud.set_login_photo(True, db)
    db.commit()
    logger.info("Login photo uploaded")


def delete_login_photo(db: Session) -> None:
    """Remove the custom login page photo and mark it as unset.

    Args:
        db: Database session.

    Raises:
        NotFoundError: If the settings row does not exist.
    """
    core_file_uploads.safe_remove_within(
        Path(core_config.SERVER_IMAGES_DIR) / _LOGIN_PHOTO_FILENAME,
        base_dir=core_config.SERVER_IMAGES_DIR,
    )
    server_settings_crud.set_login_photo(False, db)
    db.commit()
    logger.info("Login photo deleted")


def get_email_status() -> server_settings_schema.EmailStatus:
    """Report whether outgoing email is usable and, if not, why.

    Returns:
        The email status. When ``SMTP_HOST`` is unset the only problem is that it is missing.
    """
    settings = core_config.settings
    problems = settings.mail_problems
    if not settings.SMTP_HOST:
        problems = ["SMTP_HOST is not set"]
    return server_settings_schema.EmailStatus(configured=core_mail.is_mail_configured(), problems=problems)


def send_test_email(admin: users_schema.UsersRead, mail: platform_providers.MailProvider) -> None:
    """Send a test email to the admin who asked for it, synchronously.

    The send is not queued: the admin wants to know now whether the SMTP settings
    work, so the mail provider's result is returned. Its errors carry only a
    failure category and SMTP status code, so they are safe to show to an admin.

    Args:
        admin: The admin who requested the test; the only recipient.
        mail: The platform mail provider.

    Returns:
        None.

    Raises:
        ServiceUnavailableError: When email is not configured, with the reasons.
        UpstreamError: When the mail server could not be reached or refused the message.
    """
    email_status = get_email_status()
    if not email_status.configured:
        raise core_exceptions.ServiceUnavailableError("Email is not configured: " + "; ".join(email_status.problems))

    settings = core_config.settings
    subject, html_content, text_content = server_settings_email_messages.get_test_email(
        admin.name,
        f"{settings.SMTP_HOST}:{settings.SMTP_PORT}",
        settings.ENDURAIN_HOST,
        core_i18n.normalize_locale(admin.preferred_language),
    )
    message = platform_providers.MailMessage(to=[admin.email], subject=subject, text=text_content, html=html_content)
    try:
        mail.send(message)
    except platform_providers.MailError as err:
        logger.warning("Test email failed", extra=core_logger.context(error=str(err)))
        raise core_exceptions.UpstreamError(f"The mail server did not accept the test email: {err}") from err
