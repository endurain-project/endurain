"""Transactional email helpers on top of the platform mail provider.

Callers resolve ``platform.mail`` at their entry point (a durable-job handler) and
pass it in; this module never resolves the platform itself.
"""

import jasil.providers as platform_providers

import core.config as core_config
import core.logger as core_logger

logger = core_logger.get_logger(__name__)


def is_mail_configured() -> bool:
    """Whether outgoing email is configured and usable."""
    return core_config.settings.mail_configured


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
