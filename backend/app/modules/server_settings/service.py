"""Application logic for reading and editing server settings."""

import ipaddress
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
import core.route_map as core_route_map
import modules.server_settings.constants as server_settings_constants
import modules.server_settings.crud as server_settings_crud
import modules.server_settings.email_messages as server_settings_email_messages
import modules.server_settings.event_publishers as server_settings_publishers
import modules.server_settings.schema as server_settings_schema
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)

_MAP_FIELDS = frozenset({"tileserver_url", "tileserver_api_key", "map_background_color"})
_API_KEY_FIELD = "tileserver_api_key"


def _reject_unsafe_tileserver(tile_url: str) -> None:
    """Refuse a tile URL that resolves somewhere the server must not dial.

    The renderer already refuses the request at tile-fetch time, but that is a
    background job: the admin who set the value sees no error, and the bad value
    is persisted meanwhile. Checking here answers the write instead, so a URL
    pointing at cloud metadata or an internal service never reaches the row.

    It lives in the service rather than in the schema validator because the check
    resolves DNS, and the schema is also what deserializes settings on every
    *read* — a validator would put a lookup on the read path of the whole app. The
    lookup is bounded, so an unresponsive resolver cannot hold the request thread.

    Args:
        tile_url: The tile URL template being saved.

    Raises:
        InvalidInputError: When the template cannot be resolved to a URL, or the
            URL is not one the server may dial.
    """
    try:
        # Probe the template the way the renderer will: it drops ``{r}``, pins
        # ``{s}`` and escapes other placeholders before filling ``{z}/{x}/{y}``,
        # so the built-in Stadia templates (``{r}``) must pass here.
        probe_url = core_route_map.normalise_tile_url(tile_url).format(z=0, x=0, y=0)
    except (IndexError, KeyError, ValueError) as err:
        raise core_exceptions.InvalidInputError(
            "Tile server URL contains a placeholder the renderer cannot fill"
        ) from err

    reason = core_network.url_rejection_reason_bounded(probe_url, purpose="activity_thumbnail_tile")
    if reason is None:
        return
    logger.warning(
        "Refused a tile server URL that targets a non-public address",
        extra=core_logger.context(reason=reason),
    )
    raise core_exceptions.InvalidInputError(f"Tile server {reason}")


def decrypt_tileserver_api_key(encrypted_api_key: str | None) -> str | None:
    """Decrypt a stored tile API key.

    Args:
        encrypted_api_key: The stored (encrypted) key, or None / empty when unset.

    Returns:
        The plain-text key, or None when no key is set.
    """
    if not encrypted_api_key:
        return None
    return core_cryptography.decrypt_token_fernet(encrypted_api_key)


def _with_decrypted_api_key(
    server_settings: server_settings_schema.ServerSettingsRead,
) -> server_settings_schema.ServerSettingsRead:
    """Return the settings with the stored tile API key replaced by its plain text.

    Args:
        server_settings: Settings as stored.

    Returns:
        A copy carrying the decrypted key.
    """
    return server_settings.model_copy(
        update={_API_KEY_FIELD: decrypt_tileserver_api_key(server_settings.tileserver_api_key)}
    )


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
        raise core_exceptions.NotFoundError("Server settings not found.")
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
    return _with_decrypted_api_key(get_server_settings(db))


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
    """Derive the CSP ``img-src`` source for a custom tile server URL.

    The source is the tile host itself, never a registrable-domain wildcard: without
    a public-suffix list, ``tiles.example.co.uk`` would widen to ``*.co.uk``. Only the
    ``{s}`` subdomain placeholder, which stands for a set of sibling hosts, widens
    the source, and then only to that host's own subdomains.

    Args:
        url: Tile server URL template (e.g., https://tiles.example.com/map/{z}/{x}/{y}.png).

    Returns:
        ``scheme://host[:port]``, with ``*.`` standing in for the ``{s}`` label; or None
        if the URL is invalid. For example ``https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png``
        gives ``https://*.tile.openstreetmap.org`` and ``https://tiles.example.com/{z}/{x}/{y}.png``
        gives ``https://tiles.example.com``.
    """
    has_subdomain_placeholder = "{s}" in url.lower()
    try:
        parsed = urlparse(url.replace("{s}", "a").replace("{S}", "a"))
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if not parsed.scheme or not hostname:
        return None

    try:
        is_ip = ipaddress.ip_address(hostname) is not None
    except ValueError:
        is_ip = False

    if is_ip:
        host = f"[{hostname}]" if ":" in hostname else hostname
    elif has_subdomain_placeholder and "." in hostname:
        host = f"*.{hostname.split('.', 1)[1]}"
    else:
        host = hostname
    return f"{parsed.scheme}://{host}" + (f":{port}" if port else "")


def _is_covered_by(source: str, allowed_sources: list[str]) -> bool:
    """Return whether a CSP source is already allowed, exactly or by a ``*.`` wildcard.

    Args:
        source: A ``scheme://host[:port]`` source.
        allowed_sources: The sources already allowed.

    Returns:
        True when an allowed source with the same scheme matches the host.
    """
    scheme, _, host = source.partition("://")
    for allowed in allowed_sources:
        allowed_scheme, _, allowed_host = allowed.partition("://")
        if allowed_scheme != scheme:
            continue
        if allowed_host == host or (allowed_host.startswith("*.") and host.endswith(allowed_host[1:])):
            return True
    return False


def get_allowed_tile_domains(db: Session) -> list[str]:
    """Return the tile domains the CSP ``img-src`` directive allows.

    Args:
        db: Database session.

    Returns:
        The built-in provider domains plus the configured custom tile server's domain.
        Only the built-in ones when the settings row does not exist.
    """
    allowed_domains: list[str] = server_settings_schema.DEFAULT_ALLOWED_TILE_DOMAINS.copy()

    try:
        server_settings = get_server_settings(db)
    except core_exceptions.NotFoundError:
        logger.warning("Server settings row is missing; allowing only the built-in tile domains")
        return allowed_domains

    custom_domain = extract_domain_from_tile_url(server_settings.tileserver_url)
    if custom_domain and not _is_covered_by(custom_domain, allowed_domains):
        allowed_domains.append(custom_domain)
    return allowed_domains


def _changed_fields(
    attributes: server_settings_schema.ServerSettingsEdit,
    current: server_settings_schema.ServerSettingsRead,
) -> set[str]:
    """Return the sent fields whose value differs from the stored one.

    The tile API key is compared in plain text, since the stored token is encrypted
    and a fresh encryption of the same key never matches it.

    Args:
        attributes: The request body.
        current: The settings as stored.

    Returns:
        The names of the fields the request actually changes.
    """
    changed: set[str] = set()
    for field, value in attributes.model_dump(exclude_unset=True).items():
        if field == _API_KEY_FIELD:
            stored = decrypt_tileserver_api_key(current.tileserver_api_key)
            if (stored or None) != (value or None):
                changed.add(field)
        elif getattr(current, field) != value:
            changed.add(field)
    return changed


def edit_server_settings(
    attributes: server_settings_schema.ServerSettingsEdit,
    db: Session,
) -> server_settings_schema.ServerSettingsRead:
    """Persist settings and publish a tile-settings fact when the tile source changed.

    Only fields whose value differs from the stored one count as changed: a client
    that sends the whole record on every save does not trigger a tile-settings
    event, a thumbnail regeneration or a DNS lookup for settings it did not touch.

    Args:
        attributes: The settings to apply.
        db: Database session.

    Returns:
        The updated settings, with the tile API key decrypted as for an admin read.

    Raises:
        InvalidInputError: If the tile server URL cannot be dialled safely.
        NotFoundError: If the settings row does not exist.
    """
    current = get_server_settings(db)
    changed_fields = _changed_fields(attributes, current)
    if not changed_fields:
        return _with_decrypted_api_key(current)

    if "tileserver_url" in changed_fields:
        _reject_unsafe_tileserver(attributes.tileserver_url)
    if _API_KEY_FIELD in attributes.model_fields_set:
        # An unchanged key keeps its stored token instead of being re-encrypted.
        plain_api_key = attributes.tileserver_api_key
        if _API_KEY_FIELD not in changed_fields:
            stored_api_key = current.tileserver_api_key
        else:
            stored_api_key = core_cryptography.encrypt_token_fernet(plain_api_key) if plain_api_key else None
        attributes = attributes.model_copy(update={_API_KEY_FIELD: stored_api_key})

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
    return _with_decrypted_api_key(updated)


def upload_login_photo(file: UploadFile, storage: platform_providers.StorageProvider, db: Session) -> None:
    """Save the custom login page photo and mark it as set.

    The blob is written before the flag is committed: a blob without the flag is
    invisible, whereas a flag without a blob would point the login page at nothing.

    Args:
        file: The uploaded image.
        storage: The platform storage provider.
        db: Database session.

    Raises:
        DomainError: If the upload fails validation.
        NotFoundError: If the settings row does not exist.
    """
    data = core_file_uploads.read_validated_upload_sync(file, kind=core_file_uploads.UploadKind.IMAGE)
    get_server_settings(db)
    storage.save(
        server_settings_constants.LOGIN_PHOTO_STORAGE_AREA,
        server_settings_constants.LOGIN_PHOTO_STORAGE_KEY,
        data,
        file.content_type,
    )
    server_settings_crud.set_login_photo(True, db)
    db.commit()
    logger.info("Login photo uploaded")


def delete_login_photo(storage: platform_providers.StorageProvider, db: Session) -> None:
    """Remove the custom login page photo and mark it as unset.

    The flag is committed before the blob is deleted, so a failed delete leaves an
    unreferenced blob rather than a flag pointing at nothing.

    Args:
        storage: The platform storage provider.
        db: Database session.

    Raises:
        NotFoundError: If the settings row does not exist.
    """
    server_settings_crud.set_login_photo(False, db)
    db.commit()
    storage.delete(
        server_settings_constants.LOGIN_PHOTO_STORAGE_AREA, server_settings_constants.LOGIN_PHOTO_STORAGE_KEY
    )
    logger.info("Login photo deleted")


def read_login_photo(storage: platform_providers.StorageProvider) -> bytes | None:
    """Return the custom login page photo.

    Args:
        storage: The platform storage provider.

    Returns:
        The image bytes, or None when no photo is stored.
    """
    return storage.get(
        server_settings_constants.LOGIN_PHOTO_STORAGE_AREA, server_settings_constants.LOGIN_PHOTO_STORAGE_KEY
    )


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
