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
        
        # Additional Apprise configuration
        self.apprise_urls = os.getenv("APPRISE_URLS", "").split(",") if os.getenv("APPRISE_URLS") else []
        
        # Initialize Apprise
        self.apprise_obj = apprise.Apprise()
        self._setup_apprise()

    def _setup_apprise(self):
        """Setup Apprise with configured notification services"""
        # Setup SMTP notification if configured
        if self.is_smtp_configured():
            smtp_url = self._build_smtp_url()
            self.apprise_obj.add(smtp_url)
            
        # Add any additional Apprise URLs from configuration
        for url in self.apprise_urls:
            if url.strip():
                self.apprise_obj.add(url.strip())

    def _build_smtp_url(self) -> str:
        """Build Apprise SMTP URL from environment variables"""
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
        body_format: str = "text"
    ) -> bool:
        """Send a notification using Apprise"""
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
                    None, 
                    temp_apprise.notify,
                    message,
                    subject,
                    body_format
                )
            else:
                # Use general notification URLs (non-email services)
                success = await asyncio.get_event_loop().run_in_executor(
                    None, 
                    self.apprise_obj.notify,
                    message,
                    subject,
                    body_format
                )

            if success:
                core_logger.print_to_log(
                    f"Notification sent successfully: {subject}", 
                    "info"
                )
            else:
                core_logger.print_to_log(
                    f"Failed to send notification: {subject}", 
                    "warning"
                )
                
            return success

        except Exception as e:
            core_logger.print_to_log(
                f"Failed to send notification '{subject}': {e}", 
                "error", 
                exc=e
            )
            return False

    async def send_email(
        self, 
        to_emails: List[str], 
        subject: str, 
        html_content: str, 
        text_content: str = None
    ) -> bool:
        """Send an email notification (backward compatibility method)"""
        # Use HTML content primarily, fall back to text if HTML not available
        content = html_content if html_content else text_content
        body_format = "html" if html_content else "text"
        
        return await self.send_notification(
            to_emails=to_emails,
            subject=subject,
            message=content,
            body_format=body_format
        )

    async def send_password_reset_email(
        self, 
        to_email: str, 
        user_name: str, 
        reset_token: str, 
        frontend_host: str
    ) -> bool:
        """Send password reset email"""
        try:
            # Create reset link
            reset_link = f"{frontend_host}/reset-password?token={reset_token}"
            
            # Create HTML content
            html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Password Reset - Endurain</title>
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
            color: #007bff;
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
            background-color: #007bff;
            color: white;
            padding: 12px 30px;
            text-decoration: none;
            border-radius: 5px;
            display: inline-block;
            font-weight: bold;
        }}
        .reset-button a:hover {{
            background-color: #0056b3;
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
            <div class="logo">Endurain</div>
            <h1>Password Reset Request</h1>
        </div>
        
        <div class="content">
            <p>Hi {user_name},</p>
            
            <p>You requested to reset your password for your Endurain account. Click the button below to reset your password:</p>
            
            <div class="reset-button">
                <a href="{reset_link}">Reset Password</a>
            </div>
            
            <div class="warning">
                <strong>Security Notice:</strong> This link will expire in 1 hour for security reasons.
            </div>
            
            <p>If you didn't request this password reset, please ignore this email. Your password will remain unchanged.</p>
            
            <p>If the button above doesn't work, you can copy and paste the following link into your browser:</p>
            <p style="word-break: break-all; color: #007bff;">{reset_link}</p>
        </div>
        
        <div class="footer">
            <p>Best regards,<br>The Endurain Team</p>
            <p>Visit us at: <a href="{frontend_host}">{frontend_host}</a></p>
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

If you didn't request this password reset, please ignore this email.

Best regards,
The Endurain Team
            """.strip()

            # Send email
            return await self.send_email(
                to_emails=[to_email],
                subject="Password Reset - Endurain",
                html_content=html_content,
                text_content=text_content
            )

        except Exception as e:
            core_logger.print_to_log(
                f"Failed to send password reset email to {to_email}: {e}", 
                "error", 
                exc=e
            )
            return False

    def is_configured(self) -> bool:
        """Check if notification service is properly configured"""
        return self.is_smtp_configured() or len(self.apprise_urls) > 0

    def is_smtp_configured(self) -> bool:
        """Check if SMTP is properly configured"""
        return bool(self.smtp_host and self.from_email)


# Global notification service instance (renamed for backward compatibility)
email_service = NotificationService()