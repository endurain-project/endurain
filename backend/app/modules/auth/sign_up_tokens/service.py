"""Sign-up token workflows and email preparation."""

import hmac
from collections.abc import Callable, Collection
from datetime import UTC, datetime, timedelta
from typing import Literal, NoReturn, overload
from uuid import uuid4

import jasil.audit as jasil_audit
from jasil.providers import StateBackendUnavailableError, StateProvider
from sqlalchemy.orm import Session

import core.database as core_database
import core.email_cooldown as core_email_cooldown
import core.exceptions as core_exceptions
import core.i18n as core_i18n
import core.logger as core_logger
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.api_keys.integration_service as api_keys_integration
import modules.auth.computation as token_hashing
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.password_reset_tokens.integration_service as password_reset_tokens_integration
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.integration_service as sessions_integration
import modules.auth.sign_up_tokens.audit_actions as sign_up_audit_actions
import modules.auth.sign_up_tokens.contracts as sign_up_contracts
import modules.auth.sign_up_tokens.crud as sign_up_crud
import modules.auth.sign_up_tokens.email_messages as sign_up_email_messages
import modules.auth.sign_up_tokens.event_publishers as sign_up_event_publishers
import modules.auth.sign_up_tokens.schema as sign_up_schema
import modules.server_settings.integration_service as server_settings_integration
import modules.server_settings.schema as server_settings_schema
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)

EXISTING_ACCOUNT_NOTICE_COOLDOWN_SECONDS = 3600
EMAIL_CHANGE_RESEND_COOLDOWN_SECONDS = 3600
SIGN_UP_RESEND_COOLDOWN_SECONDS = 3600
EMAIL_CHANGE_TAKEN_NOTICE_COOLDOWN_SECONDS = 3600

#: Frontend pages the emailed links open, one per kind of link; each calls the route of its kind.
SIGN_UP_CONFIRM_PATH = "/signup/confirm"
EMAIL_CHANGE_CONFIRM_PATH = "/confirm-email-change"

#: How long a verification token, and so a pending email change, stays valid.
SIGN_UP_TOKEN_TTL = timedelta(hours=24)

#: How long after it was requested an email change can be reported as not made by the owner, before or after it is
#: confirmed.
EMAIL_CHANGE_REVERT_WINDOW = timedelta(days=7)


def _stage_sign_up_token(
    user_id: int,
    email: str,
    previous_email: str | None,
    db: Session,
    *,
    token: str | None = None,
    used: bool = False,
    security_generation: int | None = None,
    revertible: bool = False,
    change_id: str | None = None,
    revert_until: datetime | None = None,
) -> sign_up_contracts.SignUpTokenState:
    """Stage a user's new verification token, using up their earlier ones, and return its row.

    Args:
        user_id: The user the token belongs to.
        email: The address the token proves.
        previous_email: The account's address when an email change was requested.
        db: Database session.
        token: The raw token to store the hash of; a random one is generated when omitted.
        used: Whether the row is stored already used and confirmed, as the record of a change that was applied.
        security_generation: The account's security generation when an email change was requested; None on any
            other token.
        revertible: Whether the row starts an email change the account's owner can report as not made by them, with
            a new change identifier and a revert window of seven days from now.
        change_id: The email change the token re-issues the confirmation link of; set only with ``previous_email``.
        revert_until: The end of that change's revert window; set only with ``change_id``.

    Returns:
        The staged token row.
    """
    if token is None:
        token, token_hash = token_hashing.generate_token_and_hash()
    else:
        token_hash = token_hashing.sha256_hex(token)
    now = datetime.now(UTC)
    token_id = str(uuid4())
    if revertible:
        change_id = token_id
        revert_until = now + EMAIL_CHANGE_REVERT_WINDOW
    sign_up_token = sign_up_schema.SignUpToken(
        id=token_id,
        user_id=user_id,
        token_hash=token_hash,
        created_at=now,
        expires_at=now + SIGN_UP_TOKEN_TTL,
        used=used,
        email=email,
        previous_email=previous_email,
        security_generation=security_generation,
        change_id=change_id,
        revert_until=revert_until,
        confirmed_at=now if used else None,
    )
    sign_up_crud.mark_user_sign_up_tokens_used(user_id, db)
    return sign_up_crud.create_sign_up_token(sign_up_token, db)


def create_sign_up_token(
    user_id: int,
    email: str,
    event_id: str,
    db: Session,
    previous_email: str | None = None,
    security_generation: int | None = None,
    change_id: str | None = None,
    revert_until: datetime | None = None,
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
        security_generation: The generation the email change was requested under; set only on an email-change
            token.
        change_id: The email change this token re-issues the confirmation link of; set only on an email-change token.
        revert_until: The end of that change's revert window; set only on an email-change token.

    Returns:
        The raw token, which is not stored.
    """
    token = access_tokens_integration.derive_email_token(f"sign-up:{event_id}")
    if sign_up_crud.sign_up_token_exists(token_hashing.sha256_hex(token), db):
        return token
    _stage_sign_up_token(
        user_id,
        email,
        previous_email,
        db,
        token=token,
        security_generation=security_generation,
        change_id=change_id,
        revert_until=revert_until,
    )
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
    """Stage a pending email change, its notice to the current address and its confirmation event.

    Nothing is staged when mail is not configured. The change is not revertible, so the notice carries no link. The
    token row records the pending address; its raw value is discarded, because the delivery subscriber
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
    _stage_sign_up_token(
        user_id,
        email,
        previous_email,
        db,
        security_generation=security_generation_integration.current_generation(user_id, db),
    )
    sign_up_event_publishers.publish_email_change_requested(user_id, db)
    sign_up_event_publishers.publish_email_change_verification_requested(user_id, db)
    return True


def stage_email_changed_notice(user_id: int, email: str, previous_email: str, db: Session) -> None:
    """Stage the notice, to the previous address, that an email change already applied to the account.

    The change was applied by a writer that confirms the address itself, such as an identity-provider sync, so no
    confirmation link is involved: the row records both addresses already used, because the notice is built from
    them after the address is gone from the account. A link issued for the old address or a pending one is used
    up, so it cannot confirm over the address just applied. The caller owns the transaction, so the row, the
    event and the change commit together.

    Args:
        user_id: The user whose address changed.
        email: The address the account now uses.
        previous_email: The address the account had, which receives the notice.
        db: Database session.
    """
    token = _stage_sign_up_token(user_id, email, previous_email, db, used=True)
    sign_up_event_publishers.publish_email_changed(user_id, token.id, db)


def _holder_of(email: str, user_id: int, db: Session) -> users_schema.UserRead | None:
    """Return the other account that holds an address, or None when it is free or the user's own.

    Args:
        email: The address.
        user_id: The user who asks about it.
        db: Database session.

    Returns:
        The holder, when it is not ``user_id``.
    """
    holder = users_integration.get_user_by_email(email, db)
    return holder if holder is not None and holder.id != user_id else None


def _notify_address_holder(holder_id: int, state: StateProvider, db: Session) -> None:
    """Stage a notice event for the holder of an address another account asked to move to, once per cooldown.

    The requester's answer must not depend on the outcome, so a notice inside the cooldown, or with the cooldown
    store unreachable, is skipped without a trace. The caller commits.

    Args:
        holder_id: The user who holds the address.
        state: The platform state provider, for the notice cooldown.
        db: Database session.
    """
    try:
        claimed = core_email_cooldown.claim_email(
            state, "email_change_address_taken", holder_id, EMAIL_CHANGE_TAKEN_NOTICE_COOLDOWN_SECONDS
        )
    except StateBackendUnavailableError as err:
        logger.error(
            "Email-change notice cooldown unavailable", exc_info=err, extra=core_logger.context(user_id=holder_id)
        )
        return
    if claimed:
        sign_up_event_publishers.publish_email_change_address_taken(holder_id, db)


def request_self_service_email_change(
    user_id: int, email: str, previous_email: str, state: StateProvider, db: Session
) -> bool:
    """Stage a user's own pending email change, when mail is configured.

    The change is staged the same way whoever holds the address, so every read of it and the resend answer alike.
    A free address is mailed a confirmation link; an address another account holds is not, and its holder is
    mailed a notice instead, once per cooldown. The caller owns the transaction.

    Args:
        user_id: The user whose address changes.
        email: The pending address.
        previous_email: The user's current address, which the confirmation replaces.
        state: The platform state provider, for the holder's notice cooldown.
        db: Database session.

    Returns:
        True when the change was staged, False when mail is not configured and nothing was staged.
    """
    if not server_settings_integration.is_mail_configured(db):
        return False
    _stage_sign_up_token(
        user_id,
        email,
        previous_email,
        db,
        security_generation=security_generation_integration.current_generation(user_id, db),
        revertible=True,
    )
    sign_up_event_publishers.publish_email_change_requested(user_id, db)
    holder = _holder_of(email, user_id, db)
    if holder is None:
        sign_up_event_publishers.publish_email_change_verification_requested(user_id, db)
    else:
        _notify_address_holder(holder.id, state, db)
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
    if not server_settings_integration.is_mail_configured(db):
        return
    pending = _find_pending_email_change(user_id, db)
    if pending is None:
        return
    holder = None if pending.email is None else _holder_of(pending.email, user_id, db)
    if holder is not None:
        _notify_address_holder(holder.id, state, db)
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


def resend_sign_up_verification_email(email: str, state: StateProvider, db: Session) -> sign_up_schema.SignUpRead:
    """Send a new verification email to the account a sign-up created, without revealing whether one exists.

    An email goes out only when mail is configured, the server requires verification, the address belongs to an
    inactive account that was never deactivated and whose address is unverified, and none went out within the
    cooldown. The resend stages a live verification token in its own transaction, so the unverified-sign-up purge
    keeps the account while the mail is still queued. The answer is the same for every outcome, so it does not
    reveal which addresses are registered. An unreachable cooldown store skips the resend instead of failing the
    request. With sign-up turned off the request is refused before the address is looked at.

    Args:
        email: The address the sign-up used.
        state: The platform state provider, for the resend cooldown.
        db: Database session.

    Returns:
        The same next step for every outcome.

    Raises:
        PermissionDeniedError: If registration is disabled.
    """
    server_settings = server_settings_integration.get_server_settings(db)
    _require_sign_up_enabled(server_settings)
    response = sign_up_schema.SignUpRead(next_step=sign_up_schema.SignUpNextStep.CHECK_EMAIL)
    if not (server_settings.signup_require_email_verification and server_settings_integration.is_mail_configured(db)):
        return response
    user = users_integration.get_user_by_email(email, db)
    if user is None or user.active or user.email_verified or users_integration.is_deactivated(user.id, db):
        return response
    try:
        if not core_email_cooldown.claim_email(state, "sign_up_verification", user.id, SIGN_UP_RESEND_COOLDOWN_SECONDS):
            return response
    except StateBackendUnavailableError as err:
        logger.error("Sign-up resend cooldown unavailable", exc_info=err, extra=core_logger.context(user_id=user.id))
        return response
    # The row keeps the account alive from this commit until the delivery subscriber issues the mailed token, which
    # replaces it; its raw value is discarded.
    _stage_sign_up_token(user.id, user.email, None, db)
    sign_up_event_publishers.publish_sign_up_verification_requested(user.id, db)
    db.commit()
    return response


def request_sign_up_admin_approval_emails(user_id: int, db: Session) -> None:
    """Stage approval-email events for every configured administrator."""
    _require_mail_configured(db)
    admins = users_integration.require_admin_users(db)
    for admin in admins:
        sign_up_event_publishers.publish_sign_up_approval_requested(user_id, admin.id, db)


def request_sign_up_admin_approval(user_id: int, db: Session) -> bool:
    """Stage the administrators' approval requests for a new account awaiting approval, when mail is configured.

    Each request emails one administrator and adds an in-app notification for them. The caller commits.

    Args:
        user_id: The account awaiting approval.
        db: Database session.

    Returns:
        True when the requests were staged, False when mail is not configured and nothing was staged.
    """
    if not server_settings_integration.is_mail_configured(db):
        return False
    request_sign_up_admin_approval_emails(user_id, db)
    return True


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
    user: users_schema.UserRead,
    email: str,
    previous_email: str | None,
    event_id: str,
    frontend_host: str,
    link_path: str,
    build_email: Callable[[str, str, str, str], tuple[str, str, str]],
    db: Session,
    pending_change: sign_up_contracts.SignUpTokenState | None = None,
) -> tuple[str, str, str, str]:
    """Create a verification link to the frontend page at ``link_path`` and return the email ``build_email`` makes of it.

    ``pending_change`` is the email change the link confirms, whose generation, identifier and revert window the new
    token keeps.
    """
    token = create_sign_up_token(
        user.id,
        email,
        event_id,
        db,
        previous_email=previous_email,
        security_generation=pending_change.security_generation if pending_change else None,
        change_id=pending_change.change_id if pending_change else None,
        revert_until=pending_change.revert_until if pending_change else None,
    )
    link = f"{frontend_host}{link_path}?token={token}"
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
        user,
        user.email,
        None,
        event_id,
        frontend_host,
        SIGN_UP_CONFIRM_PATH,
        sign_up_email_messages.get_signup_confirmation_email,
        db,
    )


def prepare_email_change_verification_email(
    user_id: int,
    event_id: str,
    frontend_host: str,
    db: Session,
) -> tuple[str, str, str, str] | None:
    """Re-issue the user's pending email-change token and return its email for delivery after the session closes.

    Only a token's hash is stored, so the link is made from the pending change and the event id and mailed to the
    pending address; a retry of the event gets the same link. The new token keeps the generation the change was
    requested under, and its change identifier and revert window, so a security change since then leaves the change
    unconfirmable and it is not mailed, and the "this wasn't me" link already mailed keeps naming the change. An
    address another account holds gets none.

    Returns:
        The recipient, subject, HTML and text, or None when the user or a pending change is missing, the change
        predates a security change, or another account holds the pending address.
    """
    user = users_integration.get_user(user_id, db)
    if user is None:
        return None
    pending = _find_pending_email_change(user_id, db)
    if pending is None or pending.email is None or _holder_of(pending.email, user_id, db) is not None:
        return None
    if pending.security_generation != security_generation_integration.current_generation(user_id, db):
        return None
    return _issue_verification_email(
        user,
        pending.email,
        pending.previous_email,
        event_id,
        frontend_host,
        EMAIL_CHANGE_CONFIRM_PATH,
        sign_up_email_messages.get_email_change_confirmation_email,
        db,
        pending,
    )


def prepare_email_changed_email(
    user_id: int,
    token_id: str,
    frontend_host: str,
    db: Session,
) -> tuple[str, str, str, str] | None:
    """Return the notice to a user's previous address that a confirmed email change took effect.

    The notice of a change the owner requested carries the change's "this wasn't me" link, the one mailed when the
    change was requested; the notice of a change an administrator or a sign-in provider applied has none.

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
    revert_link = None
    if token.change_id is not None and token.revert_until is not None:
        revert_link = _revert_link(token.change_id, token.revert_until, frontend_host)
    return (
        token.previous_email,
        *sign_up_email_messages.get_email_changed_email(
            user.name,
            token.email,
            frontend_host,
            locale,
            revert_link=revert_link,
            revert_days=EMAIL_CHANGE_REVERT_WINDOW.days if revert_link else None,
        ),
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


def _revert_mac(change_id: str, revert_until: datetime) -> str:
    """Return the proof, bound to an email change and the end of its revert window, that a link was issued by this server."""
    return access_tokens_integration.derive_email_token(
        f"email-change-revert:{change_id}:{int(revert_until.timestamp())}"
    )


def _revert_link(change_id: str, revert_until: datetime, frontend_host: str) -> str:
    """Return the "this wasn't me" link of an email change; it works until ``revert_until``."""
    return f"{frontend_host}/cancel-email-change?token={change_id}.{_revert_mac(change_id, revert_until)}"


def prepare_email_change_requested_email(
    user_id: int,
    frontend_host: str,
    db: Session,
) -> tuple[str, str, str, str] | None:
    """Return the notice, for the current address, that an email change was requested.

    A change the owner requested carries a "this wasn't me" link; a change an administrator requested has no link,
    because it is not revertible. The link carries the identifier of the stored change and a proof derived from it and
    the end of its revert window, seven days after the request. Nothing else is stored for it, and it is bound to the
    change, not to the account's security generation, so confirming the change does not end it. A retry of the event,
    and a resend of the confirmation link, mail the same link.

    Args:
        user_id: The user whose address a change was requested for.
        frontend_host: Base URL of the frontend.
        db: Database session.

    Returns:
        The recipient (the current address), subject, HTML and text, or None when the user or a pending change is
        missing, or a security change since the request has already ended it.
    """
    user = users_integration.get_user(user_id, db)
    if user is None:
        return None
    pending = _find_pending_email_change(user_id, db)
    if pending is None or pending.email is None:
        return None
    if pending.security_generation != security_generation_integration.current_generation(user_id, db):
        return None
    locale = core_i18n.normalize_locale(user.preferred_language)
    if pending.change_id is None or pending.revert_until is None:
        return (
            user.email,
            *sign_up_email_messages.get_admin_email_change_requested_email(
                user.name, pending.email, frontend_host, locale
            ),
        )
    return (
        user.email,
        *sign_up_email_messages.get_email_change_requested_email(
            user.name,
            pending.email,
            _revert_link(pending.change_id, pending.revert_until, frontend_host),
            frontend_host,
            locale,
        ),
    )


def _refuse_revert(db: Session) -> NoReturn:
    """Discard what a refused "this wasn't me" link staged, audit the refusal and raise the generic answer."""
    db.rollback()
    jasil_audit.record_detached(sign_up_audit_actions.EMAIL_CHANGE_CANCEL, outcome=jasil_audit.Outcome.FAILURE)
    raise core_exceptions.InvalidInputError("Invalid or expired link")


def _email_change_of_link(token: str, now: datetime, db: Session) -> tuple[str, int] | None:
    """Return the change a link names and its owner when the link is genuine and inside its revert window.

    Args:
        token: The token of the emailed link.
        now: The current instant.
        db: Database session.

    Returns:
        The change's identifier and the user it belongs to, or None when the link is malformed, forged, expired or
        names no change.
    """
    change_id, _, mac = token.partition(".")
    if not change_id or not mac or not token.isascii():
        return None
    rows = sign_up_crud.get_email_change_tokens(change_id, now, db)
    if not rows or rows[0].revert_until is None:
        return None
    if not hmac.compare_digest(mac, _revert_mac(change_id, rows[0].revert_until)):
        return None
    return change_id, rows[0].user_id


def cancel_email_change(token: str, db: Session) -> sign_up_schema.EmailChangeCancelRead:
    """Report an email change as not made by the account's owner, with its "this wasn't me" link, and commit.

    The person who asked knew the password and passed the step-up, so the account is treated as one that someone
    else may reach: the security generation advances, every session ends and the API keys are revoked. The password
    is not changed; the notice tells the owner to reset it. The link works once, for seven days after the request.

    Before the change is confirmed the pending change is voided. After it, the link applies only while the account
    still uses the address the change moved to, and a later change of any kind ends it, and it puts the previous address back
    unless another account holds that address now; the account is secured either way.

    Args:
        token: The token of the link emailed to the account's address.
        db: Database session.

    Returns:
        Whether the change had been confirmed and whether the previous address was restored.

    Raises:
        InvalidInputError: If the link is malformed, forged, expired, already used, or names a change that a later
            change has replaced.
    """
    now = datetime.now(UTC)
    named = _email_change_of_link(token, now, db)
    if named is None:
        _refuse_revert(db)
    change_id, user_id = named
    # The generation row is the first lock taken, as in a confirmation, and the change is read again under it, so a
    # confirmation that commits first is seen.
    security_generation_integration.stage_bump(user_id, db)
    rows = sign_up_crud.get_email_change_tokens(change_id, now, db)
    confirmed = next((row for row in rows if row.confirmed_at is not None), None)
    user = users_integration.get_user(user_id, db)
    if user is None or not rows or any(row.reverted_at is not None for row in rows):
        _refuse_revert(db)
    if sign_up_crud.has_later_email_change(user_id, change_id, min(row.created_at for row in rows), now, db):
        _refuse_revert(db)
    if confirmed is not None:
        if confirmed.email is None or confirmed.previous_email is None or user.email != confirmed.email.lower():
            _refuse_revert(db)
    elif not any(
        pending.change_id == change_id for pending in sign_up_crud.get_pending_email_change_tokens([user_id], now, db)
    ):
        _refuse_revert(db)
    if sign_up_crud.mark_email_change_reverted(change_id, db) == 0:
        _refuse_revert(db)
    sign_up_crud.mark_user_sign_up_tokens_used(user_id, db)

    email_restored = False
    if confirmed is not None and confirmed.previous_email is not None:
        if _holder_of(confirmed.previous_email, user_id, db) is None:
            users_integration.stage_confirmed_email_change(user_id, confirmed.previous_email, db)
            email_restored = True
        else:
            logger.info("Previous email address not restored", extra=core_logger.context(user_id=user_id))
    sessions_revoked = sessions_integration.delete_sessions_by_user(user_id, db)
    api_keys_revoked = api_keys_integration.revoke_user_api_keys(user_id, db)
    jasil_audit.stage(
        db,
        sign_up_audit_actions.EMAIL_CHANGE_CANCEL,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
        details=sign_up_audit_actions.EmailChangeCancelDetails(
            sessions_revoked=sessions_revoked,
            api_keys_revoked=api_keys_revoked,
            change_applied=confirmed is not None,
            email_restored=email_restored,
        ),
    )
    db.commit()
    logger.info("Email change reported by the account owner", extra=core_logger.context(user_id=user_id))
    return sign_up_schema.EmailChangeCancelRead(change_applied=confirmed is not None, email_restored=email_restored)


def prepare_email_change_address_taken_email(
    user_id: int,
    frontend_host: str,
    db: Session,
) -> tuple[str, str, str, str] | None:
    """Return the address-taken notice for delivery after the database session closes."""
    user = users_integration.get_user(user_id, db)
    if user is None:
        return None
    locale = core_i18n.normalize_locale(user.preferred_language)
    return (
        user.email,
        *sign_up_email_messages.get_email_change_address_taken_email(user.name, frontend_host, locale),
    )


def revoke_user_tokens(user_id: int, db: Session) -> None:
    """Stage invalidation of a user's unused verification tokens, so an old link cannot activate the account."""
    sign_up_crud.mark_user_sign_up_tokens_used(user_id, db)


def _refuse_sign_up_token(reason: str | None = None) -> NoReturn:
    """Record a refused confirmation and raise the problem an unknown token gets."""
    details = sign_up_audit_actions.SignUpConfirmDetails(reason=reason) if reason else None
    jasil_audit.record_detached(
        sign_up_audit_actions.SIGN_UP_CONFIRM, outcome=jasil_audit.Outcome.FAILURE, details=details
    )
    raise core_exceptions.InvalidInputError("Invalid or expired sign up token")


@overload
def verify_sign_up_token(
    token: str, db: Session, *, email_change: Literal[True]
) -> sign_up_contracts.EmailChangeClaim: ...


@overload
def verify_sign_up_token(
    token: str, db: Session, *, email_change: Literal[False]
) -> sign_up_contracts.SignUpTokenClaim: ...


def verify_sign_up_token(token: str, db: Session, *, email_change: bool) -> sign_up_contracts.SignUpTokenClaim:
    """Stage consumption of a valid verification token of one kind and return what it proves.

    A token of the other kind is refused like an unknown one, and stays unused for its own route. Confirming bumps
    the account's security generation before the claim writes the token row, so the generation row is the first lock
    taken. An email change is refused when the generation it was requested under is no longer the account's: a
    password reset, an administrator's password set or any other security change since the request ends it.

    Args:
        token: The raw verification token.
        email_change: Whether the token must be an email-change token, or a sign-up token.
        db: Database session.

    Returns:
        What the token proves.

    Raises:
        InvalidInputError: If the token is unknown, used, expired or of the other kind.
    """
    token_hash = token_hashing.sha256_hex(token)
    usable = sign_up_crud.get_usable_sign_up_token(token_hash, db)
    if usable is not None and isinstance(usable, sign_up_contracts.EmailChangeClaim) is not email_change:
        _refuse_sign_up_token()
    if isinstance(usable, sign_up_contracts.EmailChangeClaim) and not security_generation_integration.matches_locked(
        usable.user_id, usable.security_generation, db
    ):
        _refuse_sign_up_token("security_changed")
    if usable is not None:
        security_generation_integration.stage_bump(usable.user_id, db)
    claim = sign_up_crud.claim_sign_up_token(token_hash, db)
    if claim is None:
        _refuse_sign_up_token()
    return claim


def _signup_response(server_settings: server_settings_schema.ServerSettingsRead) -> sign_up_schema.SignUpRead:
    """Describe a sign-up from the server's policy alone, so every outcome reads the same."""
    if server_settings.signup_require_email_verification:
        next_step = sign_up_schema.SignUpNextStep.CHECK_EMAIL
    elif server_settings.signup_require_admin_approval:
        next_step = sign_up_schema.SignUpNextStep.AWAIT_APPROVAL
    else:
        next_step = sign_up_schema.SignUpNextStep.SIGN_IN
    return sign_up_schema.SignUpRead(next_step=next_step)


def _require_sign_up_enabled(server_settings: server_settings_schema.ServerSettingsRead) -> None:
    """Raise when an administrator turned sign-up off.

    Args:
        server_settings: The server settings.

    Raises:
        PermissionDeniedError: If registration is disabled.
    """
    if not server_settings.signup_enabled:
        logger.warning("Sign-up refused because registration is disabled")
        raise core_exceptions.PermissionDeniedError("User sign-up is not enabled on this server")


def _require_username_free(username: str, db: Session) -> None:
    """Raise when an account already holds the username, normalised as the users module does.

    Args:
        username: The username a sign-up asks for.
        db: Database session.

    Raises:
        ConflictError: If the username is taken.
    """
    if users_integration.get_user_by_username(username, db) is not None:
        raise core_exceptions.ConflictError("That username is already taken")


def signup(
    user: users_schema.UserSignup,
    state: StateProvider,
    db: Session,
) -> sign_up_schema.SignUpRead:
    """Create a user and its configured verification event, or its approval requests, in one commit.

    With email verification required, the administrators are asked for approval once the address is verified;
    without it, an account awaiting approval asks them now.

    A sign-up with an email address that already has an account answers exactly like a new
    account, so the endpoint does not reveal which addresses are registered; the address's owner
    is told by email instead, at most once per cooldown. A taken username is refused whatever the address, because
    usernames are already visible to every signed-in user and the address must not be probed through it.

    When the server requires email verification the password is chosen while the address is verified, so a sign-up
    request must not carry one: whoever knows an address could otherwise set the password of the account its owner
    later activates. Without verification the request carries the password.

    Args:
        user: The sign-up details.
        state: The platform state provider, for the notice cooldown.
        db: Database session.

    Returns:
        The policy-derived description of what happens next.

    Raises:
        PermissionDeniedError: If registration is disabled.
        ConflictError: If the username is taken.
        PasswordRequiredError: If the password is missing while email verification is off.
        InvalidInputError: If a password is sent while email verification is required, or fails the configured
            policy.
    """
    server_settings = server_settings_integration.get_server_settings(db)
    _require_sign_up_enabled(server_settings)
    if server_settings.signup_require_email_verification and user.password is not None:
        raise core_exceptions.InvalidInputError("A password is chosen when the email address is verified")
    if not server_settings.signup_require_email_verification and user.password is None:
        raise core_exceptions.PasswordRequiredError("A password is required")
    if user.password is not None:
        credentials_integration.reject_breached_password(server_settings, user.password, db)

    # The username is checked first, so a refusal never depends on whether the email is registered.
    _require_username_free(user.username, db)
    try:
        created_user = users_integration.stage_signup_user(user, server_settings, db)
    except core_exceptions.ConflictError:
        db.rollback()
        # A sign-up that took the username after the check above is refused like one that found it taken.
        _require_username_free(user.username, db)
        existing = users_integration.get_user_by_email(user.email, db)
        if existing is None:
            raise core_exceptions.ConflictError("That username is already taken") from None
        request_sign_up_existing_account_notice(existing.id, state, db)
        db.commit()
        logger.info("Sign-up used an existing email address", extra=core_logger.context(user_id=existing.id))
        return _signup_response(server_settings)

    if server_settings.signup_require_email_verification:
        request_sign_up_verification_email(created_user.id, db)
    elif created_user.pending_admin_approval:
        # Nothing is left to verify, so the administrators are asked now rather than when the email is verified.
        request_sign_up_admin_approval(created_user.id, db)
    db.commit()
    logger.info("User signed up", extra=core_logger.context(user_id=created_user.id))
    return _signup_response(server_settings)


def _commit_sign_up(user_id: int, db: Session) -> None:
    """Commit a confirmed sign-up."""
    db.commit()
    logger.info("Email verification completed", extra=core_logger.context(user_id=user_id))


def confirm_sign_up(token: str, password: str, db: Session) -> sign_up_schema.SignUpRead:
    """Consume a sign-up token, set the account's password and apply the server's email-verification policy.

    The password replaces any credential the account already has, and ends its sessions and voids its unused
    password-reset tokens, as a password reset does. The address is marked verified. Only a sign-up (an inactive
    account that no administrator deactivated) is activated, and it goes on to the administrators' approval when the
    server requires it. An account an administrator activated before it was confirmed has no password yet and chooses
    one here too; an account that takes no password from a link refuses the confirmation. With sign-up turned off the
    confirmation is refused before the token or the password is looked at, and pending accounts wait until sign-up is
    turned on again or an administrator activates them.

    Args:
        token: The raw sign-up token.
        password: The password the user chooses.
        db: Database session.

    Returns:
        What happens next for the account.

    Raises:
        PermissionDeniedError: If registration is disabled.
        InvalidInputError: If the token is unknown, used, expired or not a sign-up token, or the account takes no
            password from a link.
        PasswordPolicyError: If the password fails the configured policy.
        EmailVerificationDisabledError: If a sign-up is confirmed while email verification is not enabled.
        NotFoundError: If the token's user no longer exists.
    """
    server_settings = server_settings_integration.get_server_settings(db)
    _require_sign_up_enabled(server_settings)
    # The breach check is a network call, so it runs before the claim opens the write transaction.
    credentials_integration.reject_breached_password(server_settings, password, db)
    claim = verify_sign_up_token(token, db, email_change=False)
    user_id = claim.user_id
    user = users_integration.get_user(user_id, db)
    if user is None:
        raise core_exceptions.NotFoundError("User not found")

    # An inactive account is a sign-up awaiting verification unless it was deactivated: a link never activates a
    # deactivated account or asks the administrators to approve it.
    is_sign_up = not user.active and not users_integration.is_deactivated(user_id, db)
    if is_sign_up and not server_settings.signup_require_email_verification:
        raise core_exceptions.EmailVerificationDisabledError()

    # An account an administrator activated before it was confirmed has no password yet, and without one it could
    # neither sign in nor reset its password.
    if not (is_sign_up or (user.active and not credentials_integration.has_local_password(user_id, db))):
        raise core_exceptions.InvalidInputError("This account does not choose a password from a link")
    hashed_password = credentials_integration.validate_and_hash_password_for_user(
        server_settings,
        users_schema.normalize_access_type(user.access_type),
        password,
        db,
        username=user.username,
        email=user.email,
    )
    credentials_integration.set_local_password_hash(user_id, hashed_password, db, change_required=False)
    password_reset_tokens_integration.revoke_unused_tokens(user_id, db)
    sessions_integration.delete_sessions_by_user(user_id, db)

    jasil_audit.stage(
        db,
        sign_up_audit_actions.SIGN_UP_CONFIRM,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
        details=sign_up_audit_actions.SignUpConfirmDetails(password_set=True),
    )
    users_integration.stage_email_verification(user_id, server_settings, db)
    if not is_sign_up or not server_settings.signup_require_admin_approval:
        _commit_sign_up(user_id, db)
        return sign_up_schema.SignUpRead(next_step=sign_up_schema.SignUpNextStep.SIGN_IN)

    request_sign_up_admin_approval(user.id, db)
    _commit_sign_up(user_id, db)
    return sign_up_schema.SignUpRead(next_step=sign_up_schema.SignUpNextStep.AWAIT_APPROVAL)


def confirm_email_change(token: str, db: Session) -> sign_up_schema.SignUpRead:
    """Consume an email-change token, switch the account to the confirmed address and mark it verified.

    The notice to the previous address is staged with the switch; a conflict or any later failure rolls the claim back
    with the rest of the transaction. The account's state is otherwise kept, and its security generation moves, so
    its sessions end.

    Args:
        token: The raw email-change token.
        db: Database session.

    Returns:
        The next step: signing in with the new address.

    Raises:
        InvalidInputError: If the token is unknown, used, expired, not an email-change token, or requested before a
            security change.
        ConflictError: If another account holds the address now.
        NotFoundError: If the token's user no longer exists.
    """
    server_settings = server_settings_integration.get_server_settings(db)
    claim = verify_sign_up_token(token, db, email_change=True)
    user_id = claim.user_id
    users_integration.stage_confirmed_email_change(user_id, claim.email, db)
    sign_up_event_publishers.publish_email_changed(user_id, claim.id, db)
    if users_integration.get_user(user_id, db) is None:
        raise core_exceptions.NotFoundError("User not found")
    users_integration.stage_email_verification(user_id, server_settings, db)
    _commit_sign_up(user_id, db)
    return sign_up_schema.SignUpRead(next_step=sign_up_schema.SignUpNextStep.SIGN_IN)


def delete_expired_sign_up_tokens(db: Session) -> int:
    """Delete expired verification tokens, one batch per commit, keeping an email change's rows until its revert window ends."""
    now = datetime.now(UTC)
    return core_database.delete_in_batches(lambda limit: sign_up_crud.delete_expired_sign_up_tokens(now, limit, db), db)


def purge_unverified_sign_ups(db: Session) -> int:
    """Delete the self sign-ups that never verified their address and whose link has expired, one batch per commit.

    A verification-required sign-up has no password and no sign-in provider until it verifies, so an inactive,
    unverified account created before ``SIGN_UP_TOKEN_TTL`` with neither, no deactivation or deletion request, and
    no live verification token is one nobody can still confirm. An account that signed up with a password and awaits
    an administrator's approval, and one a sign-in provider created, are kept.

    Args:
        db: Database session.

    Returns:
        How many accounts were deleted.
    """
    now = datetime.now(UTC)
    held_user_ids = (
        credentials_integration.select_credentialed_user_ids(),
        identity_provider_links_integration.select_linked_user_ids(),
        sign_up_crud.select_users_with_live_token_ids(now),
    )
    created_before = now - SIGN_UP_TOKEN_TTL
    return core_database.delete_in_batches(
        lambda limit: users_integration.stage_unverified_sign_up_purge(created_before, held_user_ids, limit, db), db
    )
