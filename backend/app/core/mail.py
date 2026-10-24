"""Transactional email helpers on top of the platform mail provider.

Callers resolve ``platform.mail`` at their entry point (a durable-job handler) and
pass it in; this module never resolves the platform itself.

It also owns the shape of the operator-edited mail configuration and how it maps onto
the substrate's ``MailSettings``. The substrate reloads its mail backend from those
settings at runtime, so there is no provider class here.
"""

import dataclasses
from enum import StrEnum
from typing import Final

import jasil.providers as platform_providers
import jasil.settings as jasil_settings

import core.logger as core_logger

logger = core_logger.get_logger(__name__)


class MailSecurity(StrEnum):
    """How the connection to the mail server is secured.

    Attributes:
        STARTTLS: ``smtp://``, upgraded with STARTTLS (port 587 by default).
        SSL: ``smtps://``, implicit TLS (port 465 typically).
        NONE: ``smtp://`` in cleartext; a private or loopback relay only, without credentials.
    """

    STARTTLS = "starttls"
    SSL = "ssl"
    NONE = "none"


@dataclasses.dataclass(frozen=True)
class MailConfig:
    """The decrypted, ready-to-use mail server configuration.

    Attributes:
        host: Mail server hostname or IP address.
        port: Mail server port.
        security: How the connection is secured.
        from_address: Sender address, empty when none is known.
        username: Authentication username, or None.
        password: Authentication password in plain text, or None.
    """

    host: str
    port: int
    security: MailSecurity
    from_address: str
    username: str | None = None
    password: str | None = dataclasses.field(default=None, repr=False)


_PROBLEM_MESSAGES: Final = {
    jasil_settings.MailProblemCode.INVALID_HOST: "Host is not a valid hostname or IP address",
    jasil_settings.MailProblemCode.INVALID_PORT: "Port must be between 1 and 65535",
    jasil_settings.MailProblemCode.MISSING_FROM_ADDRESS: (
        "A sender address is required (set one, or use an email address as the username)"
    ),
    jasil_settings.MailProblemCode.INVALID_FROM_ADDRESS: "Sender address is not a valid email address",
    jasil_settings.MailProblemCode.CREDENTIALS_INCOMPLETE: "Username and password must be set together",
    jasil_settings.MailProblemCode.CREDENTIALS_NOT_ASCII: "Username and password must contain only ASCII characters",
    jasil_settings.MailProblemCode.CLEARTEXT_WITH_CREDENTIALS: (
        "Security 'none' cannot be used with a username or password"
    ),
    jasil_settings.MailProblemCode.CLEARTEXT_PUBLIC_HOST: (
        "Security 'none' is only allowed for a private or loopback host"
    ),
}
_FALLBACK_MESSAGE: Final = "The mail settings are not valid"


def to_mail_settings(config: MailConfig | None) -> jasil_settings.MailSettings:
    """Map a mail configuration onto the substrate's mail settings.

    No validation happens here; the substrate validates what it is given.

    Args:
        config: The mail configuration, or None when mail is disabled.

    Returns:
        The equivalent settings; unset when ``config`` is None.
    """
    if config is None:
        return jasil_settings.MailSettings()
    scheme = "smtps" if config.security == MailSecurity.SSL else "smtp"
    # An IPv6 literal needs brackets inside a URI authority.
    host = f"[{config.host}]" if ":" in config.host else config.host
    # A bare address gets the product name as display name; "Name <addr>" is kept.
    from_address = config.from_address
    if from_address and "<" not in from_address:
        from_address = f"Endurain <{from_address}>"
    return jasil_settings.MailSettings(
        uri=f"{scheme}://{host}:{config.port}",
        from_address=from_address,
        secure=config.security != MailSecurity.NONE,
        username=config.username,
        password=config.password,
    )


def mail_problems(config: MailConfig) -> list[str]:
    """List why a mail configuration cannot be used, in words for an admin.

    The rules are the substrate's; this only words its results.

    Args:
        config: The mail configuration to check.

    Returns:
        One message per problem, never containing a setting's value; empty when usable.
    """
    messages: list[str] = []
    for problem in jasil_settings.mail_problems(to_mail_settings(config)):
        message = _PROBLEM_MESSAGES.get(problem.code)
        if message is None:
            logger.debug("Unmapped mail problem code", extra=core_logger.context(code=str(problem.code)))
            message = _FALLBACK_MESSAGE
        if message not in messages:
            messages.append(message)
    return messages


def send_email(
    mail: platform_providers.MailProvider,
    to_email: str,
    subject: str,
    html_content: str,
    text_content: str,
) -> bool:
    """Send one email, absorbing failures a retry cannot fix.

    Args:
        mail: The platform mail provider.
        to_email: Recipient address.
        subject: Subject line.
        html_content: HTML body.
        text_content: Plain-text alternative body.

    Returns:
        True when the message was handed to the mail server, False when it was
        dropped for a reason that retrying cannot change (mail not configured, a
        permanent 5xx refusal, or an invalid message).

    Raises:
        MailError: On a transient delivery failure, so the durable job is retried.
    """
    message = platform_providers.MailMessage(to=[to_email], subject=subject, text=text_content, html=html_content)
    try:
        mail.send(message)
    except platform_providers.MailNotConfiguredError:
        logger.warning("Email not sent: mail is not configured", extra=core_logger.context(console=True))
        return False
    except platform_providers.MailError as err:
        if err.permanent:
            logger.error(f"Email not sent, the mail server refused it permanently: {err}")
            return False
        raise
    except ValueError:
        logger.error("Email not sent: the message or recipient address is invalid")
        return False
    return True
