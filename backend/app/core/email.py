import os
import asyncio
import apprise
from typing import List

import core.logger as core_logger


class NotificationService:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "localhost")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.smtp_use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
        self.from_email = os.getenv("FROM_EMAIL", "noreply@endurain.local")
        self.from_name = os.getenv("FROM_NAME", "Endurain")
        self.frontend_host = os.getenv("ENDURAIN_HOST")

        # Additional Apprise configuration
        self.apprise_urls = (
            os.getenv("APPRISE_URLS", "").split(",")
            if os.getenv("APPRISE_URLS")
            else []
        )

        # Initialize Apprise
        self.apprise_obj = apprise.Apprise()
        self._setup_apprise()

    def _setup_apprise(self):
        """
        Configure the instance's Apprise notifications.
        If SMTP is configured (self.is_smtp_configured()), build an SMTP URL via
        self._build_smtp_url() and add it to self.apprise_obj. Then iterate over
        self.apprise_urls, strip surrounding whitespace, and add each non-empty URL
        to self.apprise_obj. Empty or whitespace-only entries are skipped.
        Side effects:
        - Calls self.apprise_obj.add(...) for each added URL, mutating the Apprise
            object attached to this instance.
        Returns:
        - None
        Raises:
        - Propagates any exceptions raised by self._build_smtp_url() or by
            self.apprise_obj.add() (for example, errors from the Apprise library or
            invalid URL formats).
        """
        # Setup SMTP notification if configured
        if self.is_smtp_configured():
            smtp_url = self._build_smtp_url()
            self.apprise_obj.add(smtp_url)

        # Add any additional Apprise URLs from configuration
        for url in self.apprise_urls:
            if url.strip():
                self.apprise_obj.add(url.strip())

    def _build_smtp_url(self) -> str:
        """Build and return a mailto-style SMTP URL from the instance SMTP settings.

        The URL includes optional authentication, host/port, and query parameters
        that represent TLS usage and sender identity.

        Rules:
        - If both `self.smtp_username` and `self.smtp_password` are set (truthy),
            include credentials as `username:password@` before the host.
        - The base URL is formed as `mailto://{auth}{smtp_host}:{smtp_port}`.
        - Optional query parameters are appended (joined with `&`) in this order:
            - `secure=yes` if `self.smtp_use_tls` is truthy.
            - `from={self.from_email}` if `self.from_email` is set.
            - `name={self.from_name}` if `self.from_name` is set.

        Returns:
                str: The constructed mailto URL suitable for use with SMTP configuration.

        Example:
                "mailto://user:pass@smtp.example.com:587?secure=yes&from=noreply@example.com&name=Example"
        """
        # Start with basic mailto scheme
        if self.smtp_username and self.smtp_password:
            auth = f"{self.smtp_username}:{self.smtp_password}@"
        else:
            auth = ""

        # Build base URL
        url = f"mailto://{auth}{self.smtp_host}:{self.smtp_port}"

        # Add query parameters
        params = []
        if self.smtp_use_tls:
            params.append("secure=yes")
        if self.from_email:
            params.append(f"from={self.from_email}")
        if self.from_name:
            params.append(f"name={self.from_name}")

        if params:
            url += "?" + "&".join(params)

        return url

    async def send_notification(
        self,
        to_emails: List[str],
        subject: str,
        message: str,
        body_format: str = "text",
    ) -> bool:
        """
        Send a notification message asynchronously.

        This method sends a notification using the Apprise library. If a list of recipient
        email addresses is provided and SMTP is configured (self.is_smtp_configured()),
        a temporary Apprise instance is created and an SMTP URL (built via
        self._build_smtp_url()) is used to send the message to each recipient. If no
        recipient emails are provided or SMTP is not configured, the method falls back
        to using the pre-configured self.apprise_obj (for non-email/general notification
        services).

        The actual Apprise notify call is executed in a threadpool via
        asyncio.get_event_loop().run_in_executor to avoid blocking the event loop.

        Args:
            to_emails (List[str]): Optional list of recipient email addresses. If empty
                or None, the method will use self.apprise_obj instead of constructing
                per-recipient SMTP URLs.
            subject (str): The notification subject/title.
            message (str): The notification message/body.
            body_format (str, optional): The body format passed to Apprise. Common
                values are "text" or "html". Defaults to "text".

        Returns:
            bool: True if Apprise reported successful delivery, False otherwise. If an
            exception occurs it is caught, logged, and False is returned.

        Side effects:
            - Calls self.is_smtp_configured() and self._build_smtp_url() when attempting
              SMTP delivery.
            - Logs success/warning/error messages using core_logger.print_to_log.
            - Constructs temporary Apprise instances for per-email SMTP sends.

        Notes:
            - The method is asynchronous (async def) and must be awaited.
            - Apprise's notify signature is invoked with (message, subject, body_format).
        """
        try:
            # For email notifications, we need to specify recipients
            if to_emails and self.is_smtp_configured():
                # Create a temporary Apprise instance for this specific email
                temp_apprise = apprise.Apprise()
                smtp_url = self._build_smtp_url()

                # Add recipients to the SMTP URL
                for email in to_emails:
                    email_url = f"{smtp_url}&to={email}"
                    temp_apprise.add(email_url)

                # Send notification
                success = await asyncio.get_event_loop().run_in_executor(
                    None, temp_apprise.notify, message, subject, body_format
                )
            else:
                # Use general notification URLs (non-email services)
                success = await asyncio.get_event_loop().run_in_executor(
                    None, self.apprise_obj.notify, message, subject, body_format
                )

            if success:
                core_logger.print_to_log(
                    f"Notification sent successfully: {subject}", "info"
                )
            else:
                core_logger.print_to_log(
                    f"Failed to send notification: {subject}", "warning"
                )

            return success
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to send notification '{subject}': {err}", "error", exc=err
            )
            return False

    async def send_email(
        self,
        to_emails: List[str],
        subject: str,
        html_content: str,
        text_content: str = None,
    ) -> bool:
        """
        Asynchronously send an email to one or more recipients, preferring HTML content.

        This method delegates to the instance's send_notification helper. If html_content
        is provided it will be used as the message body and body_format will be "html".
        If html_content is not provided but text_content is, text_content will be used and
        body_format will be "text". If neither html_content nor text_content is provided,
        message will be None and body_format will be "text" (the underlying send_notification
        may raise an error in that case).

        Parameters
        ----------
        to_emails : List[str]
            List of recipient email addresses.
        subject : str
            Subject line for the email.
        html_content : str
            HTML body of the email. Preferred when present.
        text_content : str, optional
            Plain-text body of the email. Used if html_content is not provided.

        Returns
        -------
        bool
            True if the notification was sent successfully, False otherwise. This
            is the value returned by send_notification.

        Raises
        ------
        Any
            Exceptions raised by send_notification (e.g., network/provider errors) are
            propagated to the caller.

        Example
        -------
        await self.send_email(
            to_emails=["user@example.com"],
            subject="Welcome",
            html_content="<p>Welcome!</p>",
            text_content="Welcome!"
        """
        # Use HTML content primarily, fall back to text if HTML not available
        content = html_content if html_content else text_content
        body_format = "html" if html_content else "text"

        return await self.send_notification(
            to_emails=to_emails,
            subject=subject,
            message=content,
            body_format=body_format,
        )

    async def send_password_reset_email(
        self, to_email: str, user_name: str, reset_token: str
    ) -> bool:
        """
        Send a password reset email to a user.
        This asynchronous method constructs both an HTML and a plain-text password reset
        message and attempts to send it via the instance's send_email method.
        Parameters:
            to_email (str): The recipient's email address.
            user_name (str): The recipient's display/name to personalize the greeting.
            reset_token (str): The password reset token to be appended to the frontend
                reset URL as the 'token' query parameter.
        Returns:
            bool: True if the email sending call completed successfully (i.e., send_email
            returned a truthy result); False if an exception was raised during message
            construction or sending.
        Behavior and side effects:
            - Constructs a reset link using self.frontend_host:
                f"{self.frontend_host}/reset-password?token={reset_token}"
            - Builds an HTML email (branded, with a prominent reset button and a note
              that the link expires in 1 hour) and a plain-text fallback containing the
              same link.
            - Calls self.send_email(to_emails=[to_email], subject="Endurain | Password reset",
              html_content=..., text_content=...).
            - Any exception raised during the process is caught, logged via
              core_logger.print_to_log_and_console(..., "error", exc=...), and the
              method returns False. Exceptions are not propagated to the caller.
        Example:
            await self.send_password_reset_email("user@example.com", "Alex", "sometoken123")
        """
        try:
            # Create reset link
            reset_link = f"{self.frontend_host}/reset-password?token={reset_token}"

            # Create HTML content
            html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Endurain | Password reset</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f4f4f4;
        }}
        .container {{
            background-color: #ffffff;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .logo {{
            font-size: 24px;
            font-weight: bold;
            color: #0d6efd;
            margin-bottom: 10px;
        }}
        .content {{
            margin-bottom: 30px;
        }}
        .reset-button {{
            text-align: center;
            margin: 30px 0;
        }}
        .reset-button a {{
            background-color: #0d6efd;
            color: white;
            padding: 12px 30px;
            text-decoration: none;
            border-radius: 5px;
            display: inline-block;
            font-weight: bold;
        }}
        .reset-button a:hover {{
            background-color: #6610f2;
        }}
        .footer {{
            text-align: center;
            font-size: 12px;
            color: #666;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }}
        .warning {{
            background-color: #fff3cd;
            border: 1px solid #ffeaa7;
            color: #856404;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo" style="display: flex; align-items: center; justify-content: center; gap: 10px;">
                <img src="https://github.com/joaovitoriasilva/endurain/blob/0e17fafe450b66eda7982311e6f94cee44316684/frontend/app/public/logo/logo.svg?raw=true" 
                    alt="Endurain logo" 
                    style="height: 32px; width: auto;">
                <span>Endurain</span>
            </div>
            <h1>Password reset request</h1>
        </div>
        
        <div class="content">
            <p>Hi {user_name},</p>
            
            <p>You requested to reset your password for your Endurain account. Click the button below to reset your password:</p>
            
            <div class="reset-button">
                <a href="{reset_link}">Reset Password</a>
            </div>
            
            <div class="warning">
                <strong>Security notice:</strong> This link will expire in 1 hour for security reasons.
            </div>
            
            <p>If you didn't request this password reset, please ignore this email. Your password will remain unchanged.</p>
            
            <p>If the button above doesn't work, you can copy and paste the following link into your browser:</p>
            <p style="word-break: break-all; color: #0d6efd;">{reset_link}</p>
        </div>
        
        <div class="footer">
            <p>Best regards,<br>The Endurain team</p>
            <p>Visit Endurain at: <a style="color: #0d6efd;" href="{self.frontend_host}">{self.frontend_host}</a> | Source code at: <a style="color: #0d6efd;" href="https://github.com/joaovitoriasilva/endurain">GitHub</a></p>
        </div>
    </div>
</body>
</html>
            """.strip()

            # Create text version
            text_content = f"""
Hi {user_name},

You requested to reset your password for your Endurain account.

Please click the following link to reset your password:
{reset_link}

This link will expire in 1 hour for security reasons.

If you didn't request this password reset, please ignore this email. Your password will remain unchanged.

Best regards,
The Endurain team
            """.strip()

            # Send email
            return await self.send_email(
                to_emails=[to_email],
                subject="Endurain | Password reset",
                html_content=html_content,
                text_content=text_content,
            )

        except Exception as err:
            core_logger.print_to_log_and_console(
                f"Failed to send password reset email to {to_email}: {err}",
                "error",
                exc=err,
            )
            return False

    def is_configured(self) -> bool:
        """
        Return whether the email subsystem is configured.

        This method returns True if either SMTP settings are configured
        (as determined by self.is_smtp_configured()) or there is at least
        one Apprise URL present in self.apprise_urls. Otherwise it returns False.

        Returns:
            bool: True when email can be sent via SMTP or Apprise URLs are provided,
                  False when neither configuration is present.
        """
        return self.is_smtp_configured() or len(self.apprise_urls) > 0

    def is_smtp_configured(self) -> bool:
        """
        Return whether SMTP is considered configured for this instance.

        This performs a simple presence check: it verifies that both the `smtp_host`
        and `from_email` attributes exist on the object and are truthy (neither None
        nor an empty value). This does not perform any network or credential
        validation — it only indicates that the minimal configuration values are set.

        Returns:
            bool: True if both `smtp_host` and `from_email` are set and truthy, False otherwise.

        Example:
            >>> self.smtp_host = "smtp.example.com"
            >>> self.from_email = "no-reply@example.com"
            >>> self.is_smtp_configured()
            True
        """
        return bool(self.smtp_host and self.from_email)


# Global notification service instance (renamed for backward compatibility)
email_service = NotificationService()
