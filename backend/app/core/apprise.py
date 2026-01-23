import os, secrets, hashlib
import apprise
from typing import List
from urllib.parse import quote

import core.logger as core_logger
import core.config as core_config


class AppriseService:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME")
        self.smtp_password = core_config.read_secret("SMTP_PASSWORD")
        self.smtp_secure = os.getenv("SMTP_SECURE", "true").lower()
        self.smtp_secure_type = os.getenv("SMTP_SECURE_TYPE", "starttls").lower()
        self.frontend_host = core_config.ENDURAIN_HOST

    def _build_smtp_url(self) -> str:
        """
        Build and return an SMTP-style URL used by Apprise-like notification backends.

        The method constructs a mailto/mailtos URL with a placeholder recipient ('_')
        and appends connection and credential parameters as query string values.

        Behavior:
        - If self.smtp_secure == "true", the URL scheme is "mailtos" and a "mode"
            parameter with the value of self.smtp_secure_type is added.
        - Otherwise the URL scheme is "mailto".
        - The following query parameters are appended in order: mode (optional),
            user, pass, smtp, port.

        Uses the instance attributes:
        - smtp_secure (str): "true" to enable secure mode, otherwise omitted.
        - smtp_secure_type (str): type of secure transport (e.g., "tls", "ssl").
        - smtp_username (str): username to include as the "user" query parameter.
        - smtp_password (str): password to include as the "pass" query parameter.
        - smtp_host (str): SMTP host to include as the "smtp" query parameter.
        - smtp_port (str|int): SMTP port to include as the "port" query parameter.

        Returns:
                str: The assembled URL, e.g.
                         "mailto://_?user=USERNAME&pass=PASSWORD&smtp=smtp.example.com&port=587"
                         or when secure:
                         "mailtos://_?mode=tls&user=...&pass=...&smtp=...&port=..."

        Notes and cautions:
        - Credentials are embedded in the query string; treat the returned URL as
            sensitive and avoid logging or exposing it.
        - Values are concatenated directly and are not URL-encoded by this method.
            If attribute values may contain special characters, URL-encode them before
            building the URL to ensure a valid query string.
        - The method does not validate the host, port, or credential contents.
        """
        # Build base URL
        url = f"mailto://_"
        params = []
        # if secure change url to mailtos and append secure type
        if self.smtp_secure == "true":
            url = f"mailtos://_"
            params.append(f"mode={self.smtp_secure_type}")

        # Add query parameters
        params.append(f"user={quote(self.smtp_username)}")
        params.append(f"pass={quote(self.smtp_password)}")
        params.append(f"smtp={self.smtp_host}")
        params.append(f"port={self.smtp_port}")
        params.append("name=Endurain")

        # Append any additional parameters to the url
        if params:
            url += "?" + "&".join(params)

        # return the final URL
        return url

    async def send_email(
        self,
        to_emails: List[str],
        subject: str,
        html_content: str | None = None,
        text_content: str | None = None,
    ) -> bool:
        """
        Send an email to one or more recipients using Apprise over SMTP.

        This asynchronous method prefers HTML content when provided and falls back to
        plain text. It builds a temporary Apprise instance, constructs an SMTP URL via
        self._build_smtp_url(), appends each recipient using the "&to=<email>" query
        parameter, and invokes Apprise's async_notify to send the message. The method
        performs configuration checks and logs outcomes; exceptions are caught and
        logged and result in a False return.

        Parameters:
            to_emails (List[str]): Recipient email addresses. If empty, no send is
                attempted and the method returns False.
            subject (str): The subject line for the email.
            html_content (str | None): HTML body of the email. Preferred when provided.
            text_content (str | None): Plain-text body of the email. Used if
                html_content is None.

        Returns:
            bool: True if the notification was reported as successfully sent by Apprise;
            False otherwise (including when SMTP is not configured, there are no
            recipients, required content is missing, or an exception occurs).

        Raises:
            None propagated: All exceptions are caught internally, logged via core_logger,
            and result in a False return value.

        Notes:
            - The method sets body_format to "html" when html_content is used, otherwise
              to "text".
            - The method relies on self.is_smtp_configured() to determine whether to
              attempt sending and on self._build_smtp_url() to construct the base SMTP URL.
            - Callers must await this coroutine.
        """
        # Use HTML content primarily, fall back to text if HTML not available
        content = html_content if html_content else text_content
        body_format = "html" if html_content else "text"

        try:
            # set success as false
            success = False
            # Check if emails are defined and SMTP is configured
            if to_emails and self.is_smtp_configured():
                # Create a temporary Apprise instance
                temp_apprise = apprise.Apprise()
                smtp_url = self._build_smtp_url()

                # Add recipients to the SMTP URL
                for email in to_emails:
                    email_url = f"{smtp_url}&to={email}"
                    temp_apprise.add(email_url)

                success = await temp_apprise.async_notify(
                    title=subject, body=content, body_format=body_format
                )

            if success:
                core_logger.print_to_log(f"Emails sent successfully: {subject}", "info")
            else:
                core_logger.print_to_log_and_console(
                    f"Failed to send emails: {subject}", "warning"
                )

            return success
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to send emails '{subject}': {err}", "error", exc=err
            )
            return False

    def is_configured(self) -> bool:
        """
        Return whether the notification system is configured.

        This convenience wrapper delegates to is_smtp_configured() and returns True
        when SMTP-based notifications are set up, False otherwise. It provides an
        abstraction so callers do not need to know the underlying mechanism used
        to determine configuration status.

        Returns:
            bool: True if the notification system (currently SMTP) is configured,
            False if it is not.

        Notes:
            - Currently only checks SMTP configuration via is_smtp_configured().
              Extend this method if additional notification backends need to be
              considered in the future.
        """
        return self.is_smtp_configured()

    def is_smtp_configured(self) -> bool:
        """
        Return whether SMTP is configured.

        Checks the instance attribute `smtp_host` and returns True if it is set to a truthy value
        (e.g., a non-empty string). Returns False if `smtp_host` is `None`, an empty string, or
        otherwise falsy.

        Returns:
            bool: True when SMTP host is present (SMTP considered configured), False otherwise.

        Notes:
            This method only inspects the truthiness of `smtp_host`; it does not validate the host
            format or attempt any network connection.
        """
        return bool(self.smtp_host)


def get_email_service():
    """
    Return the application's email service instance.

    This function provides access to the module-level email service object used
    for sending email notifications. It is a convenience accessor that returns
    whichever email service implementation was initialized during application
    startup (for example, a configured SMTP client, a wrapper around a third-party
    notification library, or a mock for testing).

    Returns:
        object: The initialized email service instance. The concrete type and API
        depend on how the application configured the service.

    Raises:
        RuntimeError: If the email service has not been initialized before calling
        this function.

    Usage:
        Ensure the email service is initialized during application startup. Consumers
        may call this function to obtain the service and perform send operations:

            svc = get_email_service()
            svc.send(to="user@example.com", subject="Hi", body="Hello")
    """
    return email_service


def generate_token_and_hash() -> tuple[str, str]:
    """
    Generates a secure random token and its SHA-256 hash.

    Returns:
        tuple[str, str]: A tuple containing the generated token and its SHA-256 hash.
    """
    # Generate a random 32-byte token
    token = secrets.token_urlsafe(32)

    # Create a hash of the token for database storage
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    return token, token_hash


email_service = AppriseService()
