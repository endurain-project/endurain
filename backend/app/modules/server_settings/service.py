"""Application logic for reading and editing server settings."""

import ipaddress
import os
from typing import Any
from urllib.parse import urlparse

import jasil.providers as platform_providers
from fastapi import HTTPException, UploadFile
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
_API_KEY_LABEL = "tile API key"
_MAIL_CREDENTIAL_FIELD = "password"
_MAIL_CREDENTIAL_LABEL = "SMTP password"
_SMTP_ENV_VARS = (
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "SMTP_SECURE",
    "SMTP_SECURE_TYPE",
)
#: Environment variables read through ``core_config.read_secret``, which also accepts a ``_FILE`` variant.
_FILE_SECRET_ENV_VARS = frozenset({"SMTP_PASSWORD"})


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


def _decrypt_secret(token: str | None, label: str) -> str | None:
    """Decrypt a stored secret.

    Args:
        token: The stored (encrypted) secret, or None / empty when unset.
        label: What the secret is, for the error message (for example "SMTP password").

    Returns:
        The plain-text secret, or None when none is set.

    Raises:
        ServiceUnavailableError: When the stored secret cannot be decrypted, for example
            after the encryption key changed.
    """
    if not token:
        return None
    try:
        return core_cryptography.decrypt_token_fernet(token)
    except HTTPException as err:
        raise core_exceptions.ServiceUnavailableError(
            f"The stored {label} cannot be decrypted; enter it again in the server settings"
        ) from err


def _secret_changed(stored_token: str | None, new_plain: str | None, label: str) -> bool:
    """Return whether a submitted secret differs from the stored one.

    The comparison is in plain text, since the stored token is encrypted and a fresh
    encryption of the same secret never matches it. A stored secret that can no longer
    be decrypted counts as changed, so it can always be replaced or removed.

    Args:
        stored_token: The stored (encrypted) secret.
        new_plain: The submitted plain-text secret.
        label: What the secret is, for the decryption error message.

    Returns:
        True when the submitted secret is not the stored one.
    """
    try:
        stored = _decrypt_secret(stored_token, label)
    except core_exceptions.ServiceUnavailableError:
        return True
    return (stored or None) != (new_plain or None)


def _encrypt_secret(plain: str | None) -> str | None:
    """Encrypt a secret for storage.

    Args:
        plain: The plain-text secret.

    Returns:
        The encrypted token, or None when the secret is empty.
    """
    return core_cryptography.encrypt_token_fernet(plain) if plain else None


def decrypt_tileserver_api_key(encrypted_api_key: str | None) -> str | None:
    """Decrypt a stored tile API key.

    Args:
        encrypted_api_key: The stored (encrypted) key, or None / empty when unset.

    Returns:
        The plain-text key, or None when no key is set.

    Raises:
        ServiceUnavailableError: When the stored key cannot be decrypted, for example
            after the encryption key changed.
    """
    return _decrypt_secret(encrypted_api_key, _API_KEY_LABEL)


def _to_admin_read(
    server_settings: server_settings_schema.ServerSettingsRead,
) -> server_settings_schema.ServerSettingsAdminRead:
    """Build the admin response: the stored settings without the tile API key.

    Args:
        server_settings: Settings as stored.

    Returns:
        The settings with a flag saying whether a tile API key is stored.
    """
    return server_settings_schema.ServerSettingsAdminRead(
        **server_settings.model_dump(exclude={_API_KEY_FIELD}),
        tileserver_api_key_set=bool(server_settings.tileserver_api_key),
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


def allowed_tile_domains_for_url(tile_url: str) -> list[str]:
    """Return the tile domains the CSP ``img-src`` directive allows for a tile URL.

    Args:
        tile_url: The configured tile server URL template.

    Returns:
        The built-in provider domains plus the tile URL's own domain.
    """
    allowed_domains: list[str] = server_settings_constants.DEFAULT_ALLOWED_TILE_DOMAINS.copy()
    custom_domain = extract_domain_from_tile_url(tile_url)
    if custom_domain and not _is_covered_by(custom_domain, allowed_domains):
        allowed_domains.append(custom_domain)
    return allowed_domains


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
    return allowed_tile_domains_for_url(server_settings.tileserver_url)


def _changed_fields(
    attributes: server_settings_schema.ServerSettingsEdit,
    current: server_settings_schema.ServerSettingsRead,
) -> set[str]:
    """Return the sent fields whose value differs from the stored one.

    The tile API key is compared in plain text, since the stored token is encrypted
    and a fresh encryption of the same key never matches it. A stored key that can
    no longer be decrypted counts as changed, so it can always be replaced or removed.

    Args:
        attributes: The request body.
        current: The settings as stored.

    Returns:
        The names of the fields the request actually changes.
    """
    changed: set[str] = set()
    for field, value in attributes.model_dump(exclude_unset=True).items():
        if field == _API_KEY_FIELD:
            if _secret_changed(current.tileserver_api_key, value, _API_KEY_LABEL):
                changed.add(field)
        elif getattr(current, field) != value:
            changed.add(field)
    return changed


def edit_server_settings(
    attributes: server_settings_schema.ServerSettingsEdit,
    db: Session,
) -> server_settings_schema.ServerSettingsAdminRead:
    """Persist settings and publish a tile-settings fact when the tile source changed.

    The settings row is locked for the whole edit, so two concurrent saves apply one
    after the other, each compared against what the previous one stored. Only fields
    whose value differs from the stored one count as changed: a client
    that sends the whole record on every save does not trigger a tile-settings
    event, a thumbnail regeneration or a DNS lookup for settings it did not touch.

    Args:
        attributes: The settings to apply.
        db: Database session.

    Returns:
        The updated settings, as an admin read returns them.

    Raises:
        InvalidInputError: If the tile server URL cannot be dialled safely.
        ServiceUnavailableError: If the settings row does not exist.
    """
    current = get_server_settings(db, for_update=True)
    changed_fields = _changed_fields(attributes, current)
    if not changed_fields:
        db.rollback()
        return _to_admin_read(current)

    if "tileserver_url" in changed_fields:
        _reject_unsafe_tileserver(attributes.tileserver_url)
    if _API_KEY_FIELD in attributes.model_fields_set:
        # An unchanged key keeps its stored token instead of being re-encrypted.
        plain_api_key = attributes.tileserver_api_key
        if _API_KEY_FIELD not in changed_fields:
            stored_api_key = current.tileserver_api_key
        else:
            stored_api_key = _encrypt_secret(plain_api_key)
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
    return _to_admin_read(updated)


#: Magic-number prefixes of the image formats the upload validator accepts, with their media type.
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def _sniff_image_type(data: bytes) -> str | None:
    """Return the media type of image bytes from their magic number.

    Args:
        data: The image bytes.

    Returns:
        The media type, or None when the format is not recognised.
    """
    for signature, media_type in _IMAGE_SIGNATURES:
        if data.startswith(signature):
            return media_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def upload_login_photo(file: UploadFile, storage: platform_providers.StorageProvider, db: Session) -> None:
    """Save the custom login page photo and mark it as set.

    The blob is written before the settings row is locked, so storage latency never
    holds the lock. A blob without the flag is invisible, whereas a flag without a
    blob would point the login page at nothing, so the flag is committed last. The
    stored content type is the one detected from the bytes, not the one the client
    claimed.

    Args:
        file: The uploaded image.
        storage: The platform storage provider.
        db: Database session.

    Raises:
        DomainError: If the upload fails validation or exceeds the login-photo size cap.
        ServiceUnavailableError: If the settings row does not exist.
    """
    data = core_file_uploads.read_validated_upload_sync(file, kind=core_file_uploads.UploadKind.IMAGE)
    if len(data) > server_settings_constants.LOGIN_PHOTO_MAX_BYTES:
        raise core_exceptions.PayloadTooLargeError("Login photo is too large")
    media_type = _sniff_image_type(data)
    if media_type is None:
        raise core_exceptions.UnsupportedMediaTypeError("Login photo must be a PNG, JPEG, GIF or WebP image")
    storage.save(
        server_settings_constants.LOGIN_PHOTO_STORAGE_AREA,
        server_settings_constants.LOGIN_PHOTO_STORAGE_KEY,
        data,
        media_type,
    )
    server_settings_crud.set_login_photo(True, db)
    db.commit()
    logger.info("Login photo uploaded")


def delete_login_photo(storage: platform_providers.StorageProvider, db: Session) -> None:
    """Remove the custom login page photo and mark it as unset.

    The flag is cleared and committed first, so the photo stops being served at once
    and the settings row is not locked while storage is called. The blob is deleted
    afterwards; if that fails it is an unreferenced leftover that the next upload
    overwrites.

    Args:
        storage: The platform storage provider.
        db: Database session.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    server_settings_crud.set_login_photo(False, db)
    db.commit()
    try:
        storage.delete(
            server_settings_constants.LOGIN_PHOTO_STORAGE_AREA, server_settings_constants.LOGIN_PHOTO_STORAGE_KEY
        )
    except Exception:
        logger.warning("Login photo blob could not be deleted; it is no longer served", exc_info=True)
    logger.info("Login photo deleted")


def read_login_photo(storage: platform_providers.StorageProvider, db: Session) -> tuple[bytes, str] | None:
    """Return the custom login page photo.

    The settings flag is checked first, so a server without a custom photo never
    calls storage for the unauthenticated login-page request.

    Args:
        storage: The platform storage provider.
        db: Database session.

    Returns:
        The image bytes and their media type, or None when no photo is set or stored.
    """
    if not get_server_settings(db).login_photo_set:
        return None
    data = storage.get(
        server_settings_constants.LOGIN_PHOTO_STORAGE_AREA, server_settings_constants.LOGIN_PHOTO_STORAGE_KEY
    )
    if data is None:
        return None
    # A photo stored before the type was detected on upload is served as the PNG it was.
    return data, _sniff_image_type(data) or "image/png"


def _env_var_is_set(name: str) -> bool:
    """Return whether the operator explicitly set an environment variable.

    A default value does not count. A secret read through ``read_secret`` also counts
    when only its ``_FILE`` variant is set.

    Args:
        name: The environment variable name.

    Returns:
        True when the variable was provided in the environment or ``.env``.
    """
    if name in _FILE_SECRET_ENV_VARS:
        return name in os.environ or f"{name}_FILE" in os.environ
    return name in core_config.settings.model_fields_set


def mail_env_managed() -> dict[str, str]:
    """Return the mail fields an environment variable currently sets.

    The mail block is imported as a whole when ``SMTP_HOST`` is set, so then every
    mail field is env-managed; otherwise none is.

    Returns:
        Field name to environment variable name.
    """
    if not _env_var_is_set(server_settings_constants.MAIL_ENV_VARS["host"]):
        return {}
    return dict(server_settings_constants.MAIL_ENV_VARS)


def _get_mail_settings(db: Session, *, for_update: bool = False) -> server_settings_schema.MailSettingsRead:
    """Return the mail settings as stored (the password stays encrypted).

    Args:
        db: Database session.
        for_update: Lock the row until the transaction ends; for a read that decides a write.

    Returns:
        The mail settings.

    Raises:
        ServiceUnavailableError: If the settings row does not exist. The row is
            created by the migrations, so its absence is a broken install.
    """
    mail_settings = server_settings_crud.get_mail_settings(db, for_update=for_update)
    if mail_settings is None:
        raise core_exceptions.ServiceUnavailableError("Mail settings are not initialised.")
    return mail_settings


def _to_mail_admin_read(
    mail_settings: server_settings_schema.MailSettingsRead,
) -> server_settings_schema.MailSettingsAdminRead:
    """Build the admin response: the stored mail settings without the password.

    Args:
        mail_settings: Settings as stored.

    Returns:
        The settings with a flag saying whether a password is stored.
    """
    return server_settings_schema.MailSettingsAdminRead(
        **mail_settings.model_dump(exclude={"password"}),
        password_set=bool(mail_settings.password),
        env_managed=mail_env_managed(),
    )


def _mail_config_from_row(row: server_settings_schema.MailSettingsRead) -> core_mail.MailConfig | None:
    """Build the ready-to-use mail configuration from the stored row.

    Args:
        row: The settings as stored.

    Returns:
        The configuration with the password decrypted, or None when no host is set.

    Raises:
        ServiceUnavailableError: When the stored password cannot be decrypted.
    """
    if not row.host:
        return None
    return core_mail.MailConfig(
        host=row.host,
        port=row.port,
        security=core_mail.MailSecurity(row.security),
        from_address=row.from_address or row.username or "",
        username=row.username,
        password=_decrypt_secret(row.password, _MAIL_CREDENTIAL_LABEL),
    )


def get_mail_config(db: Session) -> core_mail.MailConfig | None:
    """Return the mail configuration, ready to send with.

    Args:
        db: Database session.

    Returns:
        The configuration with the password decrypted, or None when mail is disabled
        or the settings row is missing.

    Raises:
        ServiceUnavailableError: When the stored password cannot be decrypted.
    """
    row = server_settings_crud.get_mail_settings(db)
    if row is None:
        logger.warning("Mail settings are unavailable; mail is disabled")
        return None
    return _mail_config_from_row(row)


def get_mail_settings_for_admin(db: Session) -> server_settings_schema.MailSettingsAdminRead:
    """Return the mail settings for an admin to view, without the password.

    Args:
        db: Database session.

    Returns:
        The mail settings, with a flag saying whether a password is stored.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    return _to_mail_admin_read(_get_mail_settings(db))


def _changed_mail_fields(
    attributes: server_settings_schema.MailSettingsEdit,
    current: server_settings_schema.MailSettingsRead,
) -> set[str]:
    """Return the sent mail fields whose value differs from the stored one.

    Args:
        attributes: The request body.
        current: The settings as stored.

    Returns:
        The names of the fields the request actually changes.
    """
    changed: set[str] = set()
    for field, value in attributes.model_dump(exclude_unset=True).items():
        if field == _MAIL_CREDENTIAL_FIELD:
            if _secret_changed(current.password, value, _MAIL_CREDENTIAL_LABEL):
                changed.add(field)
        elif getattr(current, field) != value:
            changed.add(field)
    return changed


def edit_mail_settings(
    attributes: server_settings_schema.MailSettingsEdit,
    db: Session,
) -> server_settings_schema.MailSettingsAdminRead:
    """Validate and persist the mail settings.

    The row is locked for the whole edit, so two concurrent saves apply one after the
    other. Only fields whose value differs from the stored one count as changed.

    Args:
        attributes: The settings to apply.
        db: Database session.

    Returns:
        The updated settings, as an admin read returns them.

    Raises:
        InvalidInputError: If a changed field is set by an environment variable, or the
            resulting configuration is not usable.
        ServiceUnavailableError: If the settings row does not exist.
    """
    current = _get_mail_settings(db, for_update=True)
    changed_fields = _changed_mail_fields(attributes, current)
    if not changed_fields:
        db.rollback()
        return _to_mail_admin_read(current)

    env_managed = mail_env_managed()
    managed_changes = [
        field for field in server_settings_constants.MAIL_ENV_VARS if field in changed_fields & env_managed.keys()
    ]
    if managed_changes:
        raise core_exceptions.InvalidInputError(
            "; ".join(
                f"{field} is set by the {env_managed[field]} environment variable; remove it to edit this setting here"
                for field in managed_changes
            )
        )

    if _MAIL_CREDENTIAL_FIELD in attributes.model_fields_set:
        plain_password = attributes.password
        # An unchanged password keeps its stored token instead of being re-encrypted.
        stored_password = (
            _encrypt_secret(plain_password) if _MAIL_CREDENTIAL_FIELD in changed_fields else current.password
        )
    else:
        plain_password = _decrypt_secret(current.password, _MAIL_CREDENTIAL_LABEL)
        stored_password = current.password

    if attributes.host:
        problems = core_mail.mail_problems(
            core_mail.MailConfig(
                host=attributes.host,
                port=attributes.port,
                security=core_mail.MailSecurity(attributes.security),
                from_address=attributes.from_address or attributes.username or "",
                username=attributes.username,
                password=plain_password,
            )
        )
        if problems:
            raise core_exceptions.InvalidInputError("; ".join(problems))

    attributes = attributes.model_copy(update={_MAIL_CREDENTIAL_FIELD: stored_password})
    updated = server_settings_crud.edit_mail_settings(attributes, db)
    db.commit()
    logger.info("Mail settings updated", extra=core_logger.context(changed_fields=sorted(changed_fields)))
    return _to_mail_admin_read(updated)


def _email_status_for(config: core_mail.MailConfig | None) -> server_settings_schema.EmailStatus:
    """Report whether a mail configuration is usable and, if not, why.

    Args:
        config: The mail configuration, or None when mail is disabled.

    Returns:
        The email status.
    """
    if config is None:
        return server_settings_schema.EmailStatus(configured=False, problems=["Host is not set"])
    problems = core_mail.mail_problems(config)
    return server_settings_schema.EmailStatus(configured=not problems, problems=problems)


def get_email_status(db: Session) -> server_settings_schema.EmailStatus:
    """Report whether outgoing email is usable and, if not, why.

    Args:
        db: Database session.

    Returns:
        The email status. When no host is set the only problem is that it is missing.

    Raises:
        ServiceUnavailableError: When the stored password cannot be decrypted.
    """
    return _email_status_for(get_mail_config(db))


def send_test_email(admin: users_schema.UsersRead, mail: platform_providers.MailProvider, db: Session) -> None:
    """Send a test email to the admin who asked for it, synchronously.

    The send is not queued: the admin wants to know now whether the mail settings
    work, so the mail provider's result is returned. Its errors carry only a
    failure category and SMTP status code, so they are safe to show to an admin.

    Args:
        admin: The admin who requested the test; the only recipient.
        mail: The platform mail provider, which sends with the stored settings.
        db: Database session.

    Returns:
        None.

    Raises:
        ServiceUnavailableError: When email is not configured, with the reasons.
        UpstreamError: When the mail server could not be reached or refused the message.
    """
    config = get_mail_config(db)
    email_status = _email_status_for(config)
    if config is None or not email_status.configured:
        raise core_exceptions.ServiceUnavailableError("Email is not configured: " + "; ".join(email_status.problems))

    subject, html_content, text_content = server_settings_email_messages.get_test_email(
        admin.name,
        f"{config.host}:{config.port}",
        core_config.settings.ENDURAIN_HOST,
        core_i18n.normalize_locale(admin.preferred_language),
    )
    message = platform_providers.MailMessage(to=[admin.email], subject=subject, text=text_content, html=html_content)
    try:
        mail.send(message)
    except platform_providers.MailError as err:
        logger.warning("Test email failed", extra=core_logger.context(error=str(err)))
        raise core_exceptions.UpstreamError(f"The mail server did not accept the test email: {err}") from err


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
    if not _env_var_is_set(server_settings_constants.MAIL_ENV_VARS["host"]):
        return []
    settings = core_config.settings
    names = [name for name in _SMTP_ENV_VARS if _env_var_is_set(name)]
    password = core_config.read_secret("SMTP_PASSWORD")
    if not settings.SMTP_SECURE:
        security = core_mail.MailSecurity.NONE
    elif settings.SMTP_SECURE_TYPE == "ssl":
        security = core_mail.MailSecurity.SSL
    else:
        security = core_mail.MailSecurity.STARTTLS

    problems = core_mail.mail_problems(
        core_mail.MailConfig(
            host=settings.SMTP_HOST or "",
            port=settings.SMTP_PORT,
            security=security,
            from_address=settings.SMTP_FROM or settings.SMTP_USERNAME or "",
            username=settings.SMTP_USERNAME,
            password=password,
        )
    )
    if problems:
        logger.error(
            "The SMTP environment variables are invalid, so the stored mail settings were left unchanged: "
            + "; ".join(problems),
            extra=core_logger.context(console=True),
        )
        return names

    current = _get_mail_settings(db, for_update=True)
    target = {
        "host": settings.SMTP_HOST,
        "port": settings.SMTP_PORT,
        "security": security.value,
        "username": settings.SMTP_USERNAME,
        "from_address": settings.SMTP_FROM,
    }
    changes: dict[str, Any] = {field: value for field, value in target.items() if getattr(current, field) != value}
    if _secret_changed(current.password, password, _MAIL_CREDENTIAL_LABEL):
        changes[_MAIL_CREDENTIAL_FIELD] = _encrypt_secret(password)
    if changes:
        # Only the differing fields are written; the values were validated above.
        server_settings_crud.edit_mail_settings(server_settings_schema.MailSettingsEdit.model_construct(**changes), db)
        logger.info(
            "Mail settings imported from the environment", extra=core_logger.context(changed_fields=sorted(changes))
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
    deprecated_names = _import_mail_env(db)
    db.commit()
    if deprecated_names:
        logger.warning(
            server_settings_constants.DEPRECATED_ENV_WARNING.format(names=", ".join(deprecated_names)),
            extra=core_logger.context(console=True),
        )
