"""Sign-up token workflows and email preparation."""

from collections.abc import Callable, Collection
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from jasil.providers import StateBackendUnavailableError, StateProvider
from sqlalchemy.orm import Session

import core.database as core_database
import core.email_cooldown as core_email_cooldown
import core.exceptions as core_exceptions
import core.i18n as core_i18n
import core.logger as core_logger
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.computation as token_hashing
import modules.auth.sign_up_tokens.contracts as sign_up_contracts
import modules.auth.sign_up_tokens.crud as sign_up_crud
import modules.auth.sign_up_tokens.email_messages as sign_up_email_messages
import modules.auth.sign_up_tokens.event_publishers as sign_up_event_publishers
import modules.auth.sign_up_tokens.schema as sign_up_schema
import modules.notifications.integration_service as notifications_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.server_settings.schema as server_settings_schema
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)

EXISTING_ACCOUNT_NOTICE_COOLDOWN_SECONDS = 3600
EMAIL_CHANGE_RESEND_COOLDOWN_SECONDS = 3600


def _stage_sign_up_token(
    user_id: int, email: str, previous_email: str | None, db: Session, *, token: str | None = None
) -> str:
    """Stage a user's new verification token, using up their earlier ones, and return its raw value.

    Args:
        user_id: The user the token belongs to.
        email: The address the token proves.
        previous_email: The account's address when an email change was requested.
        db: Database session.
        token: The raw token to store the hash of; a random one is generated when omitted.

    Returns:
        The raw token.
    """
    if token is None:
        token, token_hash = token_hashing.generate_token_and_hash()
    else:
        token_hash = token_hashing.sha256_hex(token)
    now = datetime.now(UTC)
    sign_up_token = sign_up_schema.SignUpToken(
        id=str(uuid4()),
        user_id=user_id,
        token_hash=token_hash,
        created_at=now,
        expires_at=now + timedelta(hours=24),
        used=False,
        email=email,
        previous_email=previous_email,
    )
    sign_up_crud.mark_user_sign_up_tokens_used(user_id, db)
    sign_up_crud.create_sign_up_token(sign_up_token, db)
    return token


def create_sign_up_token(
    user_id: int, email: str, event_id: str, db: Session, previous_email: str | None = None
) -> str:
    """Return the verification token for a mail event, replacing the user's earlier tokens and committing it.

    The token is derived from the event id with the server secret, so redelivering the event yields the
    same token and leaves the link already mailed working; a later request is a new event and replaces it.

    Args:
        user_id: The user the token belongs to.
        email: The address the token proves.
        event_id: The id of the event the mail is sent for, stable across its retries.
        db: Database session.
        previous_email: The account's address when an email change was requested; set only on an email-change
            token, which replaces that address with ``email`` once confirmed.

    Returns:
        The raw token, which is not stored.
    """
    token = access_tokens_integration.hmac_sha256(f"sign-up:{event_id}")
    if sign_up_crud.sign_up_token_exists(token_hashing.sha256_hex(token), db):
        return token
    _stage_sign_up_token(user_id, email, previous_email, db, token=token)
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


def request_email_change(user_id: int, email: str, previous_email: str, db: Session) -> bool:
    """Stage a pending email change and its confirmation event, when mail is configured.

    The token row records the pending address; its raw value is discarded, because the delivery subscriber
    issues the token that is mailed. The caller owns the transaction, so the row and the event commit together.

    Args:
        user_id: The user whose address changes.
        email: The pending address to confirm.
        previous_email: The user's current address, which the confirmation replaces.
        db: Database session.

    Returns:
        True when the change was staged, False when mail is not configured and nothing was staged.
    """
    if not server_settings_integration.is_mail_configured(db):
        return False
    _stage_sign_up_token(user_id, email, previous_email, db)
    sign_up_event_publishers.publish_email_change_verification_requested(user_id, db)
    return True


def _find_pending_email_change(user_id: int, db: Session) -> sign_up_contracts.SignUpTokenState | None:
    """Return a user's unused, unexpired email-change token, or None when no change is pending."""
    pending = sign_up_crud.get_pending_email_change_tokens([user_id], datetime.now(UTC), db)
    return pending[0] if pending else None


def get_pending_email_changes(
    user_ids: Collection[int], db: Session
) -> dict[int, sign_up_contracts.PendingEmailChange]:
    """Return the unconfirmed email change of each given user that has one.

    Args:
        user_ids: The users to look up.
        db: Database session.

    Returns:
        The pending address and its expiry, keyed by user id.
    """
    if not user_ids:
        return {}
    tokens = sign_up_crud.get_pending_email_change_tokens(user_ids, datetime.now(UTC), db)
    return {
        token.user_id: sign_up_contracts.PendingEmailChange(email=token.email, expires_at=token.expires_at)
        for token in tokens
        if token.email is not None
    }


def request_email_change_resend(user_id: int, state: StateProvider, db: Session) -> None:
    """Stage a new confirmation email for a user's pending email change.

    Nothing is staged without mail configured, without a pending change, when an email went out within the
    cooldown, or when the cooldown store is unreachable: the answer must not depend on the outcome, so an outage
    skips the resend instead of failing the request. The caller commits.

    Args:
        user_id: The user whose pending change is resent.
        state: The platform state provider, for the resend cooldown.
        db: Database session.
    """
    if not server_settings_integration.is_mail_configured(db) or _find_pending_email_change(user_id, db) is None:
        return
    try:
        if not core_email_cooldown.claim_email(
            state, "email_change_verification", user_id, EMAIL_CHANGE_RESEND_COOLDOWN_SECONDS
        ):
            return
    except StateBackendUnavailableError as err:
        logger.error(
            "Email-change resend cooldown unavailable", exc_info=err, extra=core_logger.context(user_id=user_id)
        )
        return
    sign_up_event_publishers.publish_email_change_verification_requested(user_id, db)


def request_sign_up_admin_approval_emails(user_id: int, db: Session) -> None:
    """Stage approval-email events for every configured administrator."""
    _require_mail_configured(db)
    admins = users_integration.require_admin_users(db)
    for admin in admins:
        sign_up_event_publishers.publish_sign_up_approval_requested(user_id, admin.id, db)


def request_sign_up_existing_account_notice(user_id: int, state: StateProvider, db: Session) -> None:
    """Stage a notice event for the owner of an email address a sign-up reused.

    Nothing is staged without mail configured, when the owner was already told within the cooldown, or
    when the cooldown store is unreachable: the sign-up answer must not depend on the outcome, so an
    outage skips the notice instead of failing the request.
    """
    if not server_settings_integration.is_mail_configured(db):
        return
    try:
        if not core_email_cooldown.claim_email(
            state, "sign_up_existing_account", user_id, EXISTING_ACCOUNT_NOTICE_COOLDOWN_SECONDS
        ):
            return
    except StateBackendUnavailableError as err:
        logger.error("Sign-up notice cooldown unavailable", exc_info=err, extra=core_logger.context(user_id=user_id))
        return
    sign_up_event_publishers.publish_sign_up_existing_account(user_id, db)


def request_sign_up_approved_email(user_id: int, db: Session) -> bool:
    """Stage an approval notice event when mail is configured; the caller commits the transition."""
    if not server_settings_integration.is_mail_configured(db):
        return False
    sign_up_event_publishers.publish_sign_up_approved(user_id, db)
    return True


def _issue_verification_email(
    user: users_schema.UsersRead,
    email: str,
    previous_email: str | None,
    event_id: str,
    frontend_host: str,
    build_email: Callable[[str, str, str, str], tuple[str, str, str]],
    db: Session,
) -> tuple[str, str, str, str]:
    """Create a verification link for ``email`` and return the email ``build_email`` makes of it."""
    token = create_sign_up_token(user.id, email, event_id, db, previous_email=previous_email)
    link = f"{frontend_host}/verify-email?token={token}"
    locale = core_i18n.normalize_locale(user.preferred_language)
    subject, html_content, text_content = build_email(user.name, link, frontend_host, locale)
    return email, subject, html_content, text_content


def prepare_sign_up_verification_email(
    user_id: int,
    event_id: str,
    frontend_host: str,
    db: Session,
) -> tuple[str, str, str, str] | None:
    """Create a verification link and return its sign-up email for delivery after the session closes."""
    user = users_integration.get_user(user_id, db)
    if user is None:
        return None
    return _issue_verification_email(
        user, user.email, None, event_id, frontend_host, sign_up_email_messages.get_signup_confirmation_email, db
    )


def prepare_email_change_verification_email(
    user_id: int,
    event_id: str,
    frontend_host: str,
    db: Session,
) -> tuple[str, str, str, str] | None:
    """Re-issue the user's pending email-change token and return its email for delivery after the session closes.

    Only a token's hash is stored, so the link is made from the pending change and the event id and mailed to the
    pending address; a retry of the event gets the same link.

    Returns:
        The recipient, subject, HTML and text, or None when the user or a pending change is missing.
    """
    user = users_integration.get_user(user_id, db)
    if user is None:
        return None
    pending = _find_pending_email_change(user_id, db)
    if pending is None or pending.email is None:
        return None
    return _issue_verification_email(
        user,
        pending.email,
        pending.previous_email,
        event_id,
        frontend_host,
        sign_up_email_messages.get_email_change_confirmation_email,
        db,
    )


def prepare_email_changed_email(
    user_id: int,
    token_id: str,
    frontend_host: str,
    db: Session,
) -> tuple[str, str, str, str] | None:
    """Return the notice to a user's previous address that a confirmed email change took effect.

    Args:
        user_id: The user whose address changed.
        token_id: The confirmed email-change token.
        frontend_host: Base URL of the frontend.
        db: Database session.

    Returns:
        The recipient (the previous address), subject, HTML and text, or None when the user or token is missing.
    """
    user = users_integration.get_user(user_id, db)
    token = sign_up_crud.get_sign_up_token_by_id(token_id, db)
    if user is None or token is None or token.user_id != user_id or token.email is None or token.previous_email is None:
        return None
    locale = core_i18n.normalize_locale(user.preferred_language)
    return (
        token.previous_email,
        *sign_up_email_messages.get_email_changed_email(user.name, token.email, frontend_host, locale),
    )


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


def prepare_sign_up_existing_account_email(
    user_id: int,
    frontend_host: str,
    db: Session,
) -> tuple[str, str, str, str] | None:
    """Return the existing-account notice for delivery after the database session closes."""
    user = users_integration.get_user(user_id, db)
    if user is None:
        return None
    locale = core_i18n.normalize_locale(user.preferred_language)
    return (
        user.email,
        *sign_up_email_messages.get_existing_account_email(user.name, frontend_host, locale),
    )


def revoke_user_tokens(user_id: int, db: Session) -> None:
    """Stage invalidation of a user's unused verification tokens, so an old link cannot activate the account."""
    sign_up_crud.mark_user_sign_up_tokens_used(user_id, db)


def verify_sign_up_token(token: str, db: Session) -> sign_up_contracts.SignUpTokenClaim:
    """Stage consumption of a valid verification token and return what it proves."""
    claim = sign_up_crud.claim_sign_up_token(token_hashing.sha256_hex(token), db)
    if claim is None:
        raise core_exceptions.InvalidInputError("Invalid or expired sign up token")
    return claim


def _signup_response(server_settings: server_settings_schema.ServerSettingsRead) -> sign_up_schema.SignUpRead:
    """Describe a sign-up from the server's policy alone, so every outcome reads the same."""
    message = "Sign-up request received."
    email_verification_required: bool | None = None
    admin_approval_required: bool | None = None
    if server_settings.signup_require_email_verification:
        message += " Check your email for verification instructions."
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


def signup(
    user: users_schema.UsersSignup,
    state: StateProvider,
    db: Session,
) -> sign_up_schema.SignUpRead:
    """Create a user and stage the configured verification event.

    A sign-up with an email address that already has an account answers exactly like a new
    account, so the endpoint does not reveal which addresses are registered; the address's owner
    is told by email instead, at most once per cooldown. A taken username with a new address is refused, because usernames
    are already visible to every signed-in user.

    Args:
        user: The sign-up details.
        state: The platform state provider, for the notice cooldown.
        db: Database session.

    Returns:
        The policy-derived description of what happens next.

    Raises:
        PermissionDeniedError: If registration is disabled.
        ConflictError: If the username is taken.
        InvalidInputError: If the password fails the configured policy.
    """
    server_settings = server_settings_integration.get_server_settings(db)
    if not server_settings.signup_enabled:
        logger.warning("Sign-up refused because registration is disabled")
        raise core_exceptions.PermissionDeniedError("User sign-up is not enabled on this server")

    try:
        created_user = users_integration.create_signup_user(user, server_settings, db)
    except core_exceptions.ConflictError:
        existing = users_integration.get_user_by_email(user.email, db)
        if existing is None:
            raise core_exceptions.ConflictError("That username is already taken") from None
        request_sign_up_existing_account_notice(existing.id, state, db)
        db.commit()
        logger.info("Sign-up used an existing email address", extra=core_logger.context(user_id=existing.id))
        return _signup_response(server_settings)

    if server_settings.signup_require_email_verification:
        request_sign_up_verification_email(created_user.id, db)
        db.commit()
    return _signup_response(server_settings)


def verify_email(token: str, db: Session) -> sign_up_schema.SignUpRead:
    """Consume a verification token and apply the server's email-verification policy.

    A token that replaces the account's address (an email-change token) first switches the account to the
    confirmed address and stages the notice to the previous one; a conflict or any later failure rolls the
    claim back with the rest of the transaction.

    The address is marked verified in every case. Only a sign-up (an inactive account that no administrator
    deactivated) is activated, and only a sign-up goes on to the administrators' approval when the server
    requires it; an active or deactivated account keeps its state.
    """
    server_settings = server_settings_integration.get_server_settings(db)
    claim = verify_sign_up_token(token, db)
    user_id = claim.user_id
    if claim.previous_email is not None:
        users_integration.stage_confirmed_email_change(user_id, claim.email, db)
        sign_up_event_publishers.publish_email_changed(user_id, claim.id, db)
    user = users_integration.get_user(user_id, db)
    if user is None:
        raise core_exceptions.NotFoundError("User not found")

    # An inactive account is a sign-up awaiting verification unless it was deactivated: a link verifies the
    # address of a deactivated account but never activates it or asks the administrators to approve it.
    is_sign_up = not user.active and not users_integration.is_deactivated(user_id, db)
    if is_sign_up and not server_settings.signup_require_email_verification:
        raise core_exceptions.PreconditionFailedError("Email verification is not enabled")

    users_integration.stage_email_verification(user_id, server_settings, db)
    if not is_sign_up:
        db.commit()
        logger.info("Email verification completed", extra=core_logger.context(user_id=user_id))
        return sign_up_schema.SignUpRead(message="Email verified successfully.")

    if not server_settings.signup_require_admin_approval:
        db.commit()
        logger.info("Email verification completed", extra=core_logger.context(user_id=user_id))
        return sign_up_schema.SignUpRead(message="Email verified successfully. You can now log in.")

    if server_settings_integration.is_mail_configured(db):
        request_sign_up_admin_approval_emails(user.id, db)
        notifications = notifications_integration.create_admin_sign_up_approval_notifications(user, db)
        db.commit()
        for notification, ws_message in notifications:
            notifications_integration.push_notification(notification.user_id, notification, ws_message)
    else:
        db.commit()

    logger.info("Email verification completed", extra=core_logger.context(user_id=user_id))
    return sign_up_schema.SignUpRead(
        message="Email verified successfully. Your account is now pending admin approval.",
        admin_approval_required=True,
    )


def delete_expired_sign_up_tokens(db: Session) -> int:
    """Delete expired verification tokens, one batch per commit."""
    now = datetime.now(UTC)
    return core_database.delete_in_batches(lambda limit: sign_up_crud.delete_expired_sign_up_tokens(now, limit, db), db)
