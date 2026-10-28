"""Sign-up token workflows and email preparation."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.i18n as core_i18n
import core.logger as core_logger
import modules.auth.computation as token_hashing
import modules.auth.sign_up_tokens.crud as sign_up_crud
import modules.auth.sign_up_tokens.email_messages as sign_up_email_messages
import modules.auth.sign_up_tokens.event_publishers as sign_up_event_publishers
import modules.auth.sign_up_tokens.schema as sign_up_schema
import modules.notifications.integration_service as notifications_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


def create_sign_up_token(user_id: int, db: Session) -> str:
    """Replace a user's verification tokens and commit the new token."""
    token, token_hash = token_hashing.generate_token_and_hash()
    now = datetime.now(UTC)
    sign_up_token = sign_up_schema.SignUpToken(
        id=str(uuid4()),
        user_id=user_id,
        token_hash=token_hash,
        created_at=now,
        expires_at=now + timedelta(hours=24),
        used=False,
    )
    sign_up_crud.mark_user_sign_up_tokens_used(user_id, db)
    sign_up_crud.create_sign_up_token(sign_up_token, db)
    db.commit()
    logger.info("Sign-up verification token created", extra=core_logger.context(user_id=user_id))
    return token


def _require_mail_configured(db: Session) -> None:
    if not server_settings_integration.is_mail_configured(db):
        raise core_exceptions.ServiceUnavailableError("Email service is not configured")


def request_sign_up_verification_email(user_id: int, db: Session) -> None:
    """Stage a verification-email event for a new account."""
    _require_mail_configured(db)
    sign_up_event_publishers.publish_sign_up_verification_requested(user_id, db)


def request_email_reverification(user_id: int, db: Session) -> bool:
    """Stage a verification-email event after an email change, when mail is configured."""
    if not server_settings_integration.is_mail_configured(db):
        return False
    sign_up_event_publishers.publish_sign_up_verification_requested(user_id, db)
    return True


def request_sign_up_admin_approval_emails(user_id: int, db: Session) -> None:
    """Stage approval-email events for every configured administrator."""
    _require_mail_configured(db)
    admins = users_integration.require_admin_users(db)
    for admin in admins:
        sign_up_event_publishers.publish_sign_up_approval_requested(user_id, admin.id, db)


def request_sign_up_approved_email(user_id: int, db: Session) -> bool:
    """Stage an approval notice event when mail is configured; the caller commits the transition."""
    if not server_settings_integration.is_mail_configured(db):
        return False
    sign_up_event_publishers.publish_sign_up_approved(user_id, db)
    return True


def prepare_sign_up_verification_email(
    user_id: int,
    frontend_host: str,
    db: Session,
) -> tuple[str, str, str, str] | None:
    """Create a verification link and return its email content for delivery after the session closes."""
    user = users_integration.get_user(user_id, db)
    if user is None:
        return None
    token = create_sign_up_token(user.id, db)
    link = f"{frontend_host}/verify-email?token={token}"
    locale = core_i18n.normalize_locale(user.preferred_language)
    subject, html_content, text_content = sign_up_email_messages.get_signup_confirmation_email(
        user.name,
        link,
        frontend_host,
        locale,
    )
    return user.email, subject, html_content, text_content


def prepare_sign_up_approval_request_email(
    user_id: int,
    admin_user_id: int,
    frontend_host: str,
    db: Session,
) -> tuple[str, str, str, str] | None:
    """Return an approval-request email for delivery after the database session closes."""
    user = users_integration.get_user(user_id, db)
    admin = users_integration.get_user(admin_user_id, db)
    if user is None or admin is None:
        return None
    locale = core_i18n.normalize_locale(admin.preferred_language)
    return (
        admin.email,
        *sign_up_email_messages.get_admin_signup_notification_email(
            admin.name,
            user.name,
            user.username,
            frontend_host,
            locale,
        ),
    )


def prepare_sign_up_approved_email(
    user_id: int,
    frontend_host: str,
    db: Session,
) -> tuple[str, str, str, str] | None:
    """Return an approval notice for delivery after the database session closes."""
    user = users_integration.get_user(user_id, db)
    if user is None:
        return None
    locale = core_i18n.normalize_locale(user.preferred_language)
    return (
        user.email,
        *sign_up_email_messages.get_user_signup_approved_email(user.name, user.username, frontend_host, locale),
    )


def revoke_user_tokens(user_id: int, db: Session) -> None:
    """Stage invalidation of a user's unused verification tokens, so an old link cannot activate the account."""
    sign_up_crud.mark_user_sign_up_tokens_used(user_id, db)


def verify_sign_up_token(token: str, db: Session) -> int:
    """Stage consumption of a valid verification token and return its user id."""
    user_id = sign_up_crud.claim_sign_up_token(token_hashing.sha256_hex(token), db)
    if user_id is None:
        raise core_exceptions.InvalidInputError("Invalid or expired sign up token")
    return user_id


def signup(
    user: users_schema.UsersSignup,
    db: Session,
) -> sign_up_schema.SignUpRead:
    """Create a user and stage the configured verification event."""
    server_settings = server_settings_integration.get_server_settings(db)
    if not server_settings.signup_enabled:
        logger.warning("Sign-up refused because registration is disabled")
        raise core_exceptions.PermissionDeniedError("User sign-up is not enabled on this server")

    created_user = users_integration.create_signup_user(user, server_settings, db)
    message = "User created successfully."
    email_verification_required: bool | None = None
    admin_approval_required: bool | None = None
    if server_settings.signup_require_email_verification:
        request_sign_up_verification_email(created_user.id, db)
        db.commit()
        message += " Email sent with verification instructions."
        email_verification_required = True
    if server_settings.signup_require_admin_approval:
        message += " Account is pending admin approval."
        admin_approval_required = True
    if not server_settings.signup_require_email_verification and not server_settings.signup_require_admin_approval:
        message += " You can now log in."
    return sign_up_schema.SignUpRead(
        message=message,
        email_verification_required=email_verification_required,
        admin_approval_required=admin_approval_required,
    )


def verify_email(token: str, db: Session) -> sign_up_schema.SignUpRead:
    """Consume a verification token and apply the server's email-verification policy."""
    server_settings = server_settings_integration.get_server_settings(db)
    user_id = verify_sign_up_token(token, db)
    user = users_integration.get_user(user_id, db)
    if user is None:
        raise core_exceptions.NotFoundError("User not found")

    if not user.active and not server_settings.signup_require_email_verification:
        raise core_exceptions.PreconditionFailedError("Email verification is not enabled")

    users_integration.stage_email_verification(user_id, server_settings, db)
    if user.active:
        db.commit()
        logger.info("Email verification completed", extra=core_logger.context(user_id=user_id))
        return sign_up_schema.SignUpRead(message="Email verified successfully.")

    if server_settings_integration.is_mail_configured(db):
        request_sign_up_admin_approval_emails(user.id, db)
        notifications = notifications_integration.create_admin_sign_up_approval_notifications(user, db)
        db.commit()
        for notification, ws_message in notifications:
            notifications_integration.push_notification(notification.user_id, notification, ws_message)
    else:
        db.commit()

    logger.info("Email verification completed", extra=core_logger.context(user_id=user_id))

    message = "Email verified successfully."
    admin_approval_required: bool | None = None
    if server_settings.signup_require_admin_approval:
        message += " Your account is now pending admin approval."
        admin_approval_required = True
    else:
        message += " You can now log in."
    return sign_up_schema.SignUpRead(message=message, admin_approval_required=admin_approval_required)


def delete_expired_sign_up_tokens(db: Session) -> int:
    """Stage deletion of expired verification tokens."""
    return sign_up_crud.delete_expired_sign_up_tokens(db)
