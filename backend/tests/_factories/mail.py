"""The test platform's recording mail outbox and the mail settings that let a request send mail."""

import jasil.runtime as platform_runtime
import jasil.testing as jasil_testing
from jasil.providers import EventBusProvider, MailMessage
from sqlalchemy.orm import Session, sessionmaker

from tests._factories.server_settings import edit_mail_settings


def configure_mail(sessions: sessionmaker[Session]) -> None:
    """Store a mail host, so the unauthenticated routes that send mail stop answering 503 (committed).

    Args:
        sessions: The application's session factory (``committed_sessions``).
    """
    with sessions() as db:
        edit_mail_settings(db, host="smtp.example.org")
        db.commit()


def outbox() -> list[MailMessage]:
    """Return the messages the active platform's memory mail recorded, oldest first."""
    return jasil_testing.memory_mail(platform_runtime.get_active_platform()).outbox


def events() -> EventBusProvider:
    """Return the active platform's event bus, which a test registers a module's subscribers on."""
    return platform_runtime.get_active_platform().events


def token_in(message: MailMessage, marker: str = "#token=") -> str:
    """Return the token of the link a mail carries, read from its plain-text body.

    Args:
        message: The mail.
        marker: What precedes the token in the link.

    Returns:
        The raw token.
    """
    assert message.text is not None
    return message.text.split(marker, 1)[1].split()[0]
