import core.apprise as core_apprise


def get_signup_confirmation_email_en(
    user_name: str, signup_link: str, email_service: core_apprise.AppriseService
) -> tuple:
    """
    Return the subject, HTML body, and plain-text body for an English sign-up confirmation email.

    Args:
        user_name (str): The recipient's display name inserted into the greeting.
        signup_link (str): The URL the user will follow to confirm their sign-up; inserted into the CTA button
            and included as a plain link for clients that do not render the button.
        email_service (core_apprise.AppriseService): Notification service instance used to obtain service
            metadata (e.g., `frontend_host`) for the email footer.

    Returns:
        tuple[str, str, str]: A 3-tuple containing:
            - subject: The email subject line.
            - html_content: The full HTML email content (string) including inline styles, logo, a prominent
              "Confirm Account" button linking to `signup_link`, a security notice about a 24-hour expiry, and
              a footer referencing `email_service.frontend_host`.
            - text_content: A plain-text alternative suitable for clients that do not render HTML, containing
              the greeting, confirmation instructions, the raw `signup_link`, expiry notice, and sign-off.

    Notes:
        - The function only constructs and returns strings; it does not send emails or perform network I/O.
        - Calling code should ensure `signup_link` and `user_name` are properly validated/sanitized as needed.
        - The HTML is crafted with inline styles for broad email-client compatibility.
    """
    subject = "Endurain - Confirm your account"
    html_content = f"""
<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
</head>

<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f4f4f4;">
    <div style="background-color: #ffffff; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);">
        <div style="text-align: center; margin-bottom: 30px;">
            <div style="font-size: 34px; font-weight: bold; margin-bottom: 10px; display: flex; align-items: center; justify-content: center; gap: 10px;">
                <img src="https://github.com/endurain-project/endurain/blob/0e17fafe450b66eda7982311e6f94cee44316684/frontend/app/public/logo/logo.svg?raw=true"
                    alt="Endurain logo" style="height: 32px; width: auto;">
                <span>Endurain</span>
            </div>
            <h3 style="margin: 0;">Confirm your account</h3>
        </div>

        <div style="margin-bottom: 30px;">
            <p>Hi {user_name},</p>

            <p>Thank you for signing up for Endurain! Please confirm your account by clicking the button below:</p>

            <div style="text-align: center; margin: 30px 0;">
                <a href="{signup_link}" style="background-color: #198754; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">Confirm Account</a>
            </div>

            <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; color: #856404; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <strong>Security notice:</strong> This confirmation link will expire in 24 hours.
            </div>

            <p>If you didn’t create an Endurain account, please ignore this email.</p>

            <p>If the button above doesn’t work, you can copy and paste the following link into your browser:</p>
            <p style="word-break: break-all; color: #198754;">{signup_link}</p>
        </div>

        <div style="text-align: center; font-size: 12px; color: #666; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
            <p>Best regards,<br>The Endurain team</p>
            <p>Visit Endurain at: <a style="color: #198754;" href="{email_service.frontend_host}">{email_service.frontend_host}</a> -
                Source code at: <a style="color: #198754;"
                    href="https://github.com/endurain-project/endurain">GitHub</a></p>
        </div>
    </div>
</body>

</html>
    """.strip()

    # Create text version
    text_content = f"""
    Hi {user_name},

    Thank you for signing up for Endurain!

    Please confirm your account by clicking the following link:
    {signup_link}

    This confirmation link will expire in 24 hours.

    If you didn’t create an Endurain account, please ignore this email.

    Best regards,
    The Endurain team
    """.strip()

    return subject, html_content, text_content


def get_admin_signup_notification_email_en(
    user_name: str,
    sign_up_user_name: str,
    sign_up_user_username: str,
    email_service: core_apprise.AppriseService,
) -> tuple:
    subject = "Endurain - New user sign-up pending approval"

    html_content = f"""
<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
</head>

<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f4f4f4;">
    <div style="background-color: #ffffff; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);">
        <div style="text-align: center; margin-bottom: 30px;">
            <div style="font-size: 34px; font-weight: bold; margin-bottom: 10px; display: flex; align-items: center; justify-content: center; gap: 10px;">
                <img src="https://github.com/endurain-project/endurain/blob/0e17fafe450b66eda7982311e6f94cee44316684/frontend/app/public/logo/logo.svg?raw=true"
                    alt="Endurain logo" style="height: 32px; width: auto;">
                <span>Endurain</span>
            </div>
            <h3 style="margin: 0;">New sign-up requires approval</h3>
        </div>

        <div style="margin-bottom: 30px;">
            <p>Hello {user_name},</p>

            <p>A new user has signed up and is awaiting approval:</p>

            <div style="background-color: #e9ecef; border: 1px solid #ccc; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <strong>User:</strong> {sign_up_user_name}
            </div>

            <p>Please log in to the Endurain admin panel to review and approve this request.</p>

            <div style="text-align: center; margin: 30px 0;">
                <a href="{email_service.frontend_host}/settings?tab=users&username={sign_up_user_username}" style="background-color: #198754; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">Go to Admin Panel</a>
            </div>

            <p>If the button above doesn’t work, you can copy and paste the following link into your browser:</p>
            <p style="word-break: break-all; color: #198754;">{email_service.frontend_host}/settings?tab=users&username={sign_up_user_username}</p>
        </div>

        <div style="text-align: center; font-size: 12px; color: #666; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
            <p>Best regards,<br>The Endurain system</p>
            <p>Visit Endurain at: <a style="color: #198754;" href="{email_service.frontend_host}">{email_service.frontend_host}</a> -
                Source code at: <a style="color: #198754;"
                    href="https://github.com/endurain-project/endurain">GitHub</a></p>
        </div>
    </div>
</body>

</html>
    """.strip()

    text_content = f"""
    Hello {user_name},

    A new user has signed up and is awaiting approval.

    User: {sign_up_user_name}

    Please log in to the Endurain admin panel to review and approve this request:
    {email_service.frontend_host}/settings?tab=users&username={sign_up_user_username}

    Best regards,
    The Endurain system
    """.strip()

    return subject, html_content, text_content


def get_user_signup_approved_email_en(
    sign_up_user_name: str,
    sign_up_user_username: str,
    email_service: core_apprise.AppriseService,
) -> tuple:
    subject = "Endurain - Your account has been approved"

    html_content = f"""
<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
</head>

<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f4f4f4;">
    <div style="background-color: #ffffff; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);">
        <div style="text-align: center; margin-bottom: 30px;">
            <div style="font-size: 34px; font-weight: bold; margin-bottom: 10px; display: flex; align-items: center; justify-content: center; gap: 10px;">
                <img src="https://github.com/endurain-project/endurain/blob/0e17fafe450b66eda7982311e6f94cee44316684/frontend/app/public/logo/logo.svg?raw=true"
                    alt="Endurain logo" style="height: 32px; width: auto;">
                <span>Endurain</span>
            </div>
            <h3 style="margin: 0;">Your account is now active</h3>
        </div>

        <div style="margin-bottom: 30px;">
            <p>Hello {sign_up_user_name},</p>

            <p>Good news! Your account has been approved and is now active.</p>

            <div style="background-color: #e9ecef; border: 1px solid #ccc; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <strong>Username:</strong> {sign_up_user_username}
            </div>

            <p>You can now log in and start using Endurain:</p>

            <div style="text-align: center; margin: 30px 0;">
                <a href="{email_service.frontend_host}/login" style="background-color: #198754; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">Log in to Endurain</a>
            </div>

            <p>If the button above doesn’t work, you can copy and paste the following link into your browser:</p>
            <p style="word-break: break-all; color: #198754;">{email_service.frontend_host}/login</p>
        </div>

        <div style="text-align: center; font-size: 12px; color: #666; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
            <p>Best regards,<br>The Endurain team</p>
            <p>Visit Endurain at: <a style="color: #198754;" href="{email_service.frontend_host}">{email_service.frontend_host}</a> -
                Source code at: <a style="color: #198754;"
                    href="https://github.com/endurain-project/endurain">GitHub</a></p>
        </div>
    </div>
</body>

</html>
    """.strip()

    text_content = f"""
    Hello {sign_up_user_name},

    Good news! Your account has been approved and is now active.

    Username: {sign_up_user_username}

    You can now log in and start using Endurain:
    {email_service.frontend_host}/login

    Best regards,
    The Endurain team
    """.strip()

    return subject, html_content, text_content
