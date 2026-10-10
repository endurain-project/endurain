"""Email-notification helpers backed by Apprise.

Wraps ``apprise`` so the rest of the application can
fire-and-forget transactional emails (password reset,
sign-up verification, admin alerts, …) without knowing
the underlying transport.
"""

import hashlib
import secrets
from functools import lru_cache
from urllib.parse import urlencode

import apprise

import core.config as core_config
import core.logger as core_logger

logger = core_logger.get_logger(__name__)

# Apprise-specific exceptions we treat as "send failed"
# rather than "programming error". Anything outside this
# set should propagate so it surfaces in tests/logs as a
# real bug instead of being silently swallowed.
_APPRISE_NETWORK_ERRORS: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
)


class AppriseService:
    """Thin Apprise wrapper for transactional email."""

    def __init__(self) -> None:
        """Bind to the current ``settings`` snapshot.

        The constructor is deliberately cheap and pure:
        it copies primitive values from ``settings`` and
        loads the password via :func:`read_secret` once.
        Re-instantiating after env changes is the
        intended way to reload configuration.
        """
        s = core_config.settings
        self.smtp_host: str | None = s.SMTP_HOST
        self.smtp_port: int = s.SMTP_PORT
        self.smtp_username: str | None = s.SMTP_USERNAME
        # Optional explicit "From" address. When unset,
        # Apprise auto-detects it from the URL. Needed for
        # providers like Brevo that validate the sender
        # against a verified-sender list.
        self.smtp_from: str | None = s.SMTP_FROM
        self.smtp_secure: bool = s.SMTP_SECURE
        self.smtp_secure_type: str = s.SMTP_SECURE_TYPE
        # Password is intentionally not stored on the
        # Settings object; it is loaded from env or a
        # Docker secret file via ``read_secret``.
        self.smtp_password: str | None = core_config.read_secret("SMTP_PASSWORD")
        # Public attribute consumed by email-body templates
        # (e.g. ``{email_service.frontend_host}/login``).
        self.frontend_host: str = s.ENDURAIN_HOST

    # SMTP URL construction
    def _build_smtp_url(self) -> str:
        """Build the ``mailto(s)://`` URL Apprise dials.

        Uses ``urlencode`` so credentials and host values
        with reserved characters (``&``, ``?``, ``#``,
        whitespace) are escaped exactly once. Auth fields
        are only emitted when both username and password
        are present — unauthenticated relays are valid.

        Returns:
            A fully-encoded Apprise URL. Treat as
            sensitive: it embeds the SMTP password in the
            query string and must never be logged.
        """
        scheme = "mailtos" if self.smtp_secure else "mailto"

        # Build the query as a list of (key, value) pairs
        # so urlencode handles every special character.
        # ``filter`` drops auth pairs when credentials
        # aren't configured (for unauthenticated relays).
        params: list[tuple[str, str]] = []
        if self.smtp_secure:
            params.append(("mode", self.smtp_secure_type))
        if self.smtp_username and self.smtp_password:
            params.append(("user", self.smtp_username))
            params.append(("pass", self.smtp_password))
        if self.smtp_host:
            params.append(("smtp", self.smtp_host))
        params.append(("port", str(self.smtp_port)))
        params.append(("name", "Endurain"))
        # Set the "From" address so providers that validate
        # it (e.g. Brevo) accept the message. Omitted when
        # unset so Apprise keeps auto-detecting the sender.
        if self.smtp_from:
            params.append(("from", self.smtp_from))

        return f"{scheme}://_?{urlencode(params)}"

    # Send email
    async def send_email(
        self,
        to_emails: list[str],
        subject: str,
        html_content: str | None = None,
        text_content: str | None = None,
    ) -> bool:
        """Send a transactional email to one or more recipients.

        HTML content is preferred; text content is the
        fallback. Returns ``False`` (and logs a warning)
        when SMTP isn't configured, no recipients are
        supplied, or the underlying transport reports a
        network failure. Programming errors (TypeError,
        ValueError, etc.) deliberately propagate.

        Args:
            to_emails: Recipient addresses.
            subject: Email subject line.
            html_content: HTML body (preferred).
            text_content: Plain-text fallback body.

        Returns:
            True on successful delivery, False otherwise.
        """
        if not to_emails:
            logger.warning("send_email called with no recipients")
            return False
        if not self.is_smtp_configured():
            logger.warning("send_email skipped: SMTP not configured")
            return False

        content = html_content if html_content else text_content
        if not content:
            logger.warning("send_email called with neither html_content nor text_content")
            return False
        body_format = "html" if html_content else "text"

        try:
            temp_apprise = apprise.Apprise()
            smtp_url = self._build_smtp_url()
            for email in to_emails:
                # ``to`` accepts a single address per add()
                # call. ``urlencode`` keeps the recipient
                # safe even if the email contains special
                # characters (extremely rare but cheap to
                # defend against).
                recipient_qs = urlencode([("to", email)])
                temp_apprise.add(f"{smtp_url}&{recipient_qs}")

            success = await temp_apprise.async_notify(title=subject, body=content, body_format=body_format)
        except _APPRISE_NETWORK_ERRORS as err:
            # Log the exception type only; ``err`` may
            # contain the recipient or partial credentials
            # in its message on some libc/transport
            # combinations.
            logger.error(f"send_email transport failure for subject '{subject}': {type(err).__name__}", exc_info=err)
            return False

        if success:
            logger.info(f"Email sent: {subject} (recipients={len(to_emails)})")
        else:
            logger.warning(f"Email send returned failure: {subject}", extra=core_logger.context(console=True))
        return bool(success)

    # Configuration introspection
    def is_configured(self) -> bool:
        """Whether the notification system can send mail."""
        return self.is_smtp_configured()

    def is_smtp_configured(self) -> bool:
        """Whether SMTP is sufficiently configured to attempt a send.

        Requires a host. When a username is configured we
        also require a password — half-configured auth is
        treated as misconfiguration so callers don't
        spend cycles attempting unauthenticated sends
        against an authenticated relay.
        """
        if not self.smtp_host:
            return False
        return not (self.smtp_username and not self.smtp_password)


# Module-level accessors
@lru_cache(maxsize=1)
def get_email_service() -> AppriseService:
    """Return the process-wide :class:`AppriseService` instance.

    Constructed lazily so importing this module never
    triggers env-var or secret-file reads. Used as a
    FastAPI dependency in routers; safe to call from
    anywhere because the result is cached.
    """
    return AppriseService()


def __getattr__(name: str):
    """Lazy module attribute hook.

    Preserves the legacy ``core_apprise.email_service``
    attribute access pattern without instantiating the
    service at import time.
    """
    if name == "email_service":
        return get_email_service()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Token helpers
def generate_token_and_hash() -> tuple[str, str]:
    """Generate a URL-safe random token and its SHA-256 hash.

    Returns:
        ``(token, token_hash)``. Store the hash in the
        database; hand the raw token to the user via the
        outbound channel (email link, etc.). Comparing
        the SHA-256 of an incoming token to the stored
        hash avoids leaking the secret if the DB is read
        by an attacker.
    """
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return token, token_hash
