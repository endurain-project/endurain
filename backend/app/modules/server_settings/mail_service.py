"""Mail settings, the email status and the test email."""

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.config as core_config
import core.etag as core_etag
import core.exceptions as core_exceptions
import core.i18n as core_i18n
import core.logger as core_logger
import core.mail as core_mail
import modules.server_settings.change_utils as server_settings_change_utils
import modules.server_settings.constants as server_settings_constants
import modules.server_settings.crud as server_settings_crud
import modules.server_settings.email_messages as server_settings_email_messages
import modules.server_settings.schema as server_settings_schema
import modules.server_settings.service as server_settings_service
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


def mail_env_managed() -> dict[str, str]:
    """Return the mail fields an environment variable currently sets.

    The mail block is imported as a whole when ``SMTP_HOST`` is set, so then every
    mail field is env-managed; otherwise none is.

    Returns:
        Field name to environment variable name.
    """
    if not server_settings_service.env_var_is_set(server_settings_constants.MAIL_ENV_VARS["host"]):
        return {}
    return dict(server_settings_constants.MAIL_ENV_VARS)


def read_mail_settings(db: Session, *, for_update: bool = False) -> server_settings_schema.MailSettingsRead:
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


def build_mail_config(
    host: str,
    port: int,
    security: str,
    from_address: str | None,
    username: str | None,
    password: str | None,
) -> core_mail.MailConfig:
    """Build the mail configuration, defaulting the sender to the username.

    Args:
        host: Mail server hostname.
        port: Mail server port.
        security: Connection security.
        from_address: Sender address, or None to use the username.
        username: Authentication username.
        password: Authentication password in plain text.

    Returns:
        The mail configuration.
    """
    return core_mail.MailConfig(
        host=host,
        port=port,
        security=core_mail.MailSecurity(security),
        from_address=from_address or username or "",
        username=username,
        password=password,
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
    return build_mail_config(
        row.host,
        row.port,
        row.security,
        row.from_address,
        row.username,
        server_settings_change_utils.decrypt_secret(row.password, server_settings_constants.MAIL_CREDENTIAL_LABEL),
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


def is_mail_configured(db: Session) -> bool:
    """Return whether a mail server is set, without validating it.

    Cheap enough for unauthenticated routes: no decryption and no DNS lookup. The settings
    are validated when saved or imported, and the mail provider validates again on send.

    Args:
        db: Database session.

    Returns:
        True when a mail host is stored.
    """
    row = server_settings_crud.get_mail_settings(db)
    return row is not None and bool(row.host)


def get_mail_settings_for_admin(db: Session) -> server_settings_schema.MailSettingsAdminRead:
    """Return the mail settings for an admin to view, without the password.

    Args:
        db: Database session.

    Returns:
        The mail settings, with a flag saying whether a password is stored.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    return _to_mail_admin_read(read_mail_settings(db))


def edit_mail_settings(
    attributes: server_settings_schema.MailSettingsEdit,
    db: Session,
    *,
    if_match: str,
) -> server_settings_schema.MailSettingsAdminRead:
    """Validate and persist the mail settings.

    Validation can resolve DNS, so it runs on a snapshot before the settings row is
    locked; a slow resolver never holds the lock. The row is then locked for the rest of
    the edit, so two concurrent saves apply one after the other. Only fields whose value
    differs from the stored one count as changed.

    Args:
        attributes: The settings to apply.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated settings, as an admin read returns them.

    Raises:
        InvalidInputError: If the resulting configuration is not usable.
        ConflictError: If a changed field is set by an environment variable.
        PreconditionFailedError: If the mail settings changed since the client read them.
        ServiceUnavailableError: If the settings row does not exist.
    """
    snapshot = read_mail_settings(db)
    # End the read transaction: the validation below may resolve DNS.
    db.rollback()
    core_etag.require_if_match(if_match, snapshot.version, "mail settings")
    keeps_password = server_settings_constants.MAIL_CREDENTIAL_FIELD not in attributes.model_fields_set
    plain_password = (
        server_settings_change_utils.decrypt_secret(snapshot.password, server_settings_constants.MAIL_CREDENTIAL_LABEL)
        if keeps_password
        else attributes.password
    )
    if attributes.host:
        problems = core_mail.mail_problems(
            build_mail_config(
                attributes.host,
                attributes.port,
                attributes.security,
                attributes.from_address,
                attributes.username,
                plain_password,
            )
        )
        if problems:
            raise core_exceptions.InvalidInputError("; ".join(problems))

    current = read_mail_settings(db, for_update=True)
    core_etag.require_if_match(if_match, current.version, "mail settings")
    if keeps_password and current.password != snapshot.password:
        # The password the validation used is no longer the stored one.
        raise core_exceptions.PreconditionFailedError("The mail settings were modified by someone else; retry")
    changed_fields = server_settings_change_utils.changed_fields(
        attributes,
        current,
        {server_settings_constants.MAIL_CREDENTIAL_FIELD: server_settings_constants.MAIL_CREDENTIAL_LABEL},
    )
    if not changed_fields:
        db.rollback()
        return _to_mail_admin_read(current)

    server_settings_change_utils.refuse_env_managed(
        changed_fields, mail_env_managed(), server_settings_constants.MAIL_ENV_VARS
    )
    if not keeps_password:
        # An unchanged password keeps its stored token instead of being re-encrypted.
        stored_password = (
            server_settings_change_utils.encrypt_secret(plain_password)
            if server_settings_constants.MAIL_CREDENTIAL_FIELD in changed_fields
            else current.password
        )
        attributes = attributes.model_copy(update={server_settings_constants.MAIL_CREDENTIAL_FIELD: stored_password})
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
    # End the read transaction: the mail server may take a while to answer.
    db.rollback()
    try:
        mail.send(message)
    except platform_providers.MailError as err:
        logger.warning("Test email failed", extra=core_logger.context(error=str(err)))
        raise core_exceptions.UpstreamError(f"The mail server did not accept the test email: {err}") from err
