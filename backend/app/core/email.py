import os
import asyncio
import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Environment, FileSystemLoader, select_autoescape
from typing import List

import core.logger as core_logger


class EmailService:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "localhost")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.smtp_use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
        self.from_email = os.getenv("FROM_EMAIL", "noreply@endurain.local")
        self.from_name = os.getenv("FROM_NAME", "Endurain")
        
        # Jinja2 environment for templates
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )

    async def send_email(
        self, 
        to_emails: List[str], 
        subject: str, 
        html_content: str, 
        text_content: str = None
    ) -> bool:
        """Send an email using SMTP"""
        try:
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{self.from_name} <{self.from_email}>"
            message["To"] = ", ".join(to_emails)

            # Add text part if provided
            if text_content:
                text_part = MIMEText(text_content, "plain")
                message.attach(text_part)

            # Add HTML part
            html_part = MIMEText(html_content, "html")
            message.attach(html_part)

            # Send email
            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                start_tls=self.smtp_use_tls,
                username=self.smtp_username if self.smtp_username else None,
                password=self.smtp_password if self.smtp_password else None,
            )

            core_logger.print_to_log(
                f"Email sent successfully to {', '.join(to_emails)}", 
                "info"
            )
            return True

        except Exception as e:
            core_logger.print_to_log(
                f"Failed to send email to {', '.join(to_emails)}: {e}", 
                "error", 
                exc=e
            )
            return False

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
            
            # Render email template
            template = self.jinja_env.get_template("password_reset.html")
            html_content = template.render(
                user_name=user_name,
                reset_link=reset_link,
                frontend_host=frontend_host
            )
            
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
        """Check if email service is properly configured"""
        return bool(self.smtp_host and self.from_email)


# Global email service instance
email_service = EmailService()