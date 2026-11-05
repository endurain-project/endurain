"""Session refresh with refresh token rotation."""

from __future__ import annotations

from datetime import datetime

import jasil.audit as jasil_audit
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.audit_actions as authentication_audit_actions
import modules.auth.authentication.refusal_audit as authentication_refusal_audit
import modules.auth.authentication.schema as auth_schema
import modules.auth.authentication.token_service as authentication_token_service
import modules.auth.constants as auth_constants
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_providers.integration_service as identity_providers_integration
import modules.auth.rotated_refresh_tokens.integration_service as rotated_refresh_tokens_integration
import modules.auth.sessions.contracts as sessions_contracts
import modules.auth.sessions.integration_service as sessions_integration
import modules.server_settings.contracts as server_settings_contracts
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


def _replay_rotation(
    client_type: auth_constants.ClientType,
    session: sessions_contracts.SessionRead,
    refresh_token_value: str,
    token_user_id: int,
    token_manager: access_tokens_integration.TokenManager,
    policy: server_settings_contracts.SessionPolicy,
    db: Session,
) -> auth_schema.AuthOutcome[auth_schema.TokenRead]:
    """Answer a refresh whose token was already rotated with the replacement minted by that rotation.

    The session is not rotated again (no new rotated record, no ``rotation_count`` bump), so duplicate
    and concurrent refreshes converge on one live refresh token.

    Args:
        client_type: Client type (``"web"`` or ``"mobile"``).
        session: The session the token belongs to.
        refresh_token_value: The raw refresh token that was already rotated.
        token_user_id: User ID extracted from the refresh token.
        token_manager: Utility for creating tokens.
        policy: The server's session policy.
        db: Database session.

    Returns:
        The outcome carrying the replacement refresh token.

    Raises:
        UnauthenticatedError: If the replacement is gone or the user cannot authenticate.
    """
    replay = rotated_refresh_tokens_integration.get_grace_replay_token(refresh_token_value, db)

    if replay is None:
        # Replacement was cleaned up (or never stored); fall back to the
        # standard invalid-token response.
        logger.warning(
            "Refresh token replay refused: no replacement stored for user <token_user_id>",
            extra=core_logger.context(token_user_id=token_user_id),
        )
        authentication_refusal_audit.record_refresh_refusal(
            token_user_id,
            jasil_audit.Outcome.FAILURE,
            authentication_audit_actions.RefreshRefusalReason.REPLAY_UNAVAILABLE,
        )
        raise core_exceptions.UnauthenticatedError("Invalid refresh token", scheme="Bearer")

    replay_refresh_token, replay_refresh_token_exp = replay

    # Validate the user is still present and active before re-issuing.
    replay_user = users_integration.get_user(token_user_id, db)

    if replay_user is None:
        logger.warning(
            "User ID <token_user_id> not found during token refresh replay",
            extra=core_logger.context(token_user_id=token_user_id),
        )
        authentication_refusal_audit.record_refresh_refusal(
            token_user_id, jasil_audit.Outcome.FAILURE, authentication_audit_actions.RefreshRefusalReason.USER_NOT_FOUND
        )
        raise core_exceptions.UnauthenticatedError("Unable to authenticate", scheme="Bearer")

    try:
        users_integration.require_active_user(replay_user)
    except core_exceptions.PermissionDeniedError:
        authentication_refusal_audit.record_refresh_refusal(
            token_user_id, jasil_audit.Outcome.DENIED, authentication_audit_actions.RefreshRefusalReason.USER_INACTIVE
        )
        raise

    # Mint a fresh, stateless access token (safe to re-issue every retry).
    replay_access_token_exp, replay_access_token = authentication_token_service.mint_access_token(
        replay_user, token_manager, session.id, policy
    )

    # Web clients lost their CSRF token along with the rotation response, so
    # mint a fresh one and bind it to the session (the refresh token itself
    # is unchanged). Mobile clients do not use CSRF, so as on login the token
    # is minted but never bound or returned.
    replay_csrf_token = token_manager.create_csrf_token()
    if client_type == auth_constants.ClientType.WEB:
        sessions_integration.update_session_csrf_token(session.id, replay_csrf_token, db)
        db.commit()

    return authentication_token_service.build_token_response(
        client_type,
        session.id,
        replay_access_token,
        replay_access_token_exp,
        replay_refresh_token,
        replay_refresh_token_exp,
        replay_csrf_token,
    )


def refresh_token(
    ip_address: str,
    user_agent: str,
    token_user_id: int,
    token_session_id: str,
    refresh_token_value: str,
    refresh_token_exp: datetime,
    password_hasher: credentials_integration.PasswordHasher,
    token_manager: access_tokens_integration.TokenManager,
    client_type: auth_constants.ClientType,
    db: Session,
    x_csrf_token: str | None = None,
) -> auth_schema.AuthOutcome[auth_schema.TokenRead]:
    r"""Handles the refresh token process for user sessions.

    This endpoint validates the provided refresh token, checks session status,
    validates the CSRF token (web clients only), and issues new tokens.

    OAuth 2.1 Bootstrap Pattern for Page Reload:
        On page reload, in-memory tokens are lost but httpOnly cookie persists.
        - If no CSRF header: Allow refresh (page reload scenario)
        - If CSRF header provided: Validate it (legitimate request with cached token)
        - Security: httpOnly cookie + SameSite=Strict prevents CSRF at browser level
        - CSRF validation adds defense-in-depth but is not the primary protection

    Args:
        ip_address: Client address, recorded on the session.
        user_agent: Client user agent, recorded on the session.
        token_user_id: User ID extracted from the refresh token.
        token_session_id: Session ID extracted from the refresh token.
        refresh_token_value: The raw refresh token value.
        refresh_token_exp: Expiry of the presented refresh token; its rotated record is kept until then.
        password_hasher: Utility for verifying token hashes.
        token_manager: Utility for creating tokens.
        db: Database session.
        client_type: Client type (\"web\" or \"mobile\").
        x_csrf_token: CSRF token header (web clients only, optional on page reload).


    Returns:
        The token body (session_id, access_token, csrf_token, token_type, expires_in, refresh_token_expires_in) and,
        for web clients, the refresh cookie.

    Raises:
        DomainError: If session not found, refresh token invalid,
                       user is inactive, or CSRF token is invalid (when provided).
    """
    # Get the session from the database
    session = sessions_integration.get_session_by_id_not_expired(token_session_id, db)

    # Check if the session was found
    if session is None:
        authentication_refusal_audit.record_refresh_refusal(
            token_user_id,
            jasil_audit.Outcome.FAILURE,
            authentication_audit_actions.RefreshRefusalReason.SESSION_NOT_FOUND,
        )
        raise core_exceptions.NotFoundError("Session not found")

    # Defense-in-depth: ensure the session belongs to the user named in
    # the refresh token's `sub` claim. The refresh-token hash stored on
    # the session is already bound to this user, so a mismatched token
    # would fail hash verification below — but asserting ownership here
    # makes the invariant explicit and fails fast (rather than relying on
    # the implicit binding) if a token's `sub`/`sid` claims are ever
    # decoupled from the persisted session.
    if session.user_id != token_user_id:
        logger.warning(
            "Refresh token session owner mismatch: token sub=<token_user_id>, session user_id=<user_id>",
            extra=core_logger.context(token_user_id=token_user_id, user_id=session.user_id),
        )
        authentication_refusal_audit.record_refresh_refusal(
            token_user_id,
            jasil_audit.Outcome.FAILURE,
            authentication_audit_actions.RefreshRefusalReason.SESSION_OWNER_MISMATCH,
        )
        raise core_exceptions.UnauthenticatedError("Invalid refresh token", scheme="Bearer")

    # Validate session hasn't exceeded idle or absolute timeout
    policy = server_settings_integration.get_session_policy(db)
    try:
        sessions_integration.validate_session_timeout(session, policy)
    except core_exceptions.UnauthenticatedError:
        authentication_refusal_audit.record_refresh_refusal(
            token_user_id,
            jasil_audit.Outcome.FAILURE,
            authentication_audit_actions.RefreshRefusalReason.SESSION_EXPIRED,
        )
        raise

    # Verify CSRF token for web clients only
    # Mobile clients don't use CSRF tokens
    # OAuth 2.1 Bootstrap Pattern for page reload:
    # - On EVERY page reload, in-memory tokens (incl. CSRF) are lost but the
    #   httpOnly refresh cookie persists. The client therefore POSTs to
    #   /refresh without an X-CSRF-Token header to bootstrap a new in-memory
    #   token. This must continue to work even after a CSRF binding has been
    #   minted on the session, otherwise the user is logged out on reload.
    # - When the client DOES send a header, it MUST be valid. An empty/wrong
    #   value is rejected (prevents partial-CSRF where script can read the
    #   cookie but not the bound token).
    # - CSRF protection at this endpoint is defense-in-depth; the primary
    #   protections are HttpOnly + SameSite=Strict on the refresh cookie,
    #   which prevent a cross-site attacker from issuing this POST at all.
    if (
        client_type == auth_constants.ClientType.WEB
        and x_csrf_token
        and session.csrf_token_hash is not None
        and not sessions_integration.verify_csrf_token(x_csrf_token, session.csrf_token_hash)
    ):
        # CSRF token was provided: validate it
        logger.warning(
            "Token refresh refused: invalid CSRF token for user <token_user_id>",
            extra=core_logger.context(token_user_id=token_user_id),
        )
        authentication_refusal_audit.record_refresh_refusal(
            token_user_id,
            jasil_audit.Outcome.DENIED,
            authentication_audit_actions.RefreshRefusalReason.INVALID_CSRF_TOKEN,
        )
        raise core_exceptions.PermissionDeniedError("Invalid CSRF token")

    # Verify session has a refresh token (not pending PKCE exchange)
    if not session.refresh_token:
        authentication_refusal_audit.record_refresh_refusal(
            token_user_id,
            jasil_audit.Outcome.FAILURE,
            authentication_audit_actions.RefreshRefusalReason.TOKENS_NOT_EXCHANGED,
        )
        raise core_exceptions.UnauthenticatedError(
            "Tokens not yet exchanged via PKCE. Complete SSO/PKCE flow first.", scheme="Bearer"
        )

    # Check for token reuse BEFORE validating token
    # Uses HMAC-SHA256 internally for deterministic, secure lookup
    is_reused, in_grace = rotated_refresh_tokens_integration.check_token_reuse(refresh_token_value, db)

    if is_reused and not in_grace:
        # Token theft detected - invalidate entire family
        sessions_integration.invalidate_token_family(session.token_family_id, db)
        # The family stays invalidated although this request is refused.
        with authentication_refusal_audit.refresh_token_context(token_user_id):
            jasil_audit.stage(
                db,
                authentication_audit_actions.REFRESH_TOKEN_REUSE,
                outcome=jasil_audit.Outcome.DENIED,
                **authentication_refusal_audit.user_target(token_user_id),
            )
        db.commit()
        logger.warning(
            "Refresh token reuse detected for user <token_user_id>; token family invalidated",
            extra=core_logger.context(token_user_id=token_user_id),
        )
        raise core_exceptions.UnauthenticatedError("Token reuse detected. All sessions invalidated.", scheme="Bearer")

    if is_reused and in_grace:
        # A retry inside the grace window (a lost rotation response, or a duplicate refresh) is answered
        # with the replacement minted on the original rotation; the session is not rotated again.
        return _replay_rotation(client_type, session, refresh_token_value, token_user_id, token_manager, policy, db)

    is_valid = password_hasher.verify_password(refresh_token_value, session.refresh_token)

    if not is_valid:
        logger.warning(
            "Token refresh refused: refresh token does not match session for user <token_user_id>",
            extra=core_logger.context(token_user_id=token_user_id),
        )
        authentication_refusal_audit.record_refresh_refusal(
            token_user_id, jasil_audit.Outcome.FAILURE, authentication_audit_actions.RefreshRefusalReason.INVALID_TOKEN
        )
        raise core_exceptions.UnauthenticatedError("Invalid refresh token", scheme="Bearer")

    # get user
    user = users_integration.get_user(token_user_id, db)

    if user is None:
        logger.warning(
            "User ID <token_user_id> not found during token refresh",
            extra=core_logger.context(token_user_id=token_user_id),
        )
        authentication_refusal_audit.record_refresh_refusal(
            token_user_id, jasil_audit.Outcome.FAILURE, authentication_audit_actions.RefreshRefusalReason.USER_NOT_FOUND
        )
        raise core_exceptions.UnauthenticatedError("Unable to authenticate", scheme="Bearer")

    # Check if the user is active
    try:
        users_integration.require_active_user(user)
    except core_exceptions.PermissionDeniedError:
        authentication_refusal_audit.record_refresh_refusal(
            token_user_id, jasil_audit.Outcome.DENIED, authentication_audit_actions.RefreshRefusalReason.USER_INACTIVE
        )
        raise

    # Create the new token bundle first so the rotated record can persist the
    # replacement refresh token used for idempotent in-grace replay.
    (
        session_id,
        new_access_token_exp,
        new_access_token,
        new_refresh_token_exp,
        new_refresh_token,
        new_csrf_token,
    ) = authentication_token_service.create_tokens(user, token_manager, policy, session.id)

    # Store the rotated (old) refresh token together with the encrypted
    # replacement so a retry within the grace window can replay it.
    # store_rotated_token hashes the old token with HMAC-SHA256 for lookup
    # and encrypts the replacement at rest.
    try:
        rotated_refresh_tokens_integration.store_rotated_token(
            refresh_token_value,
            session.token_family_id,
            session.rotation_count,
            db,
            refresh_token_exp=refresh_token_exp,
            replacement_refresh_token=new_refresh_token,
            replacement_refresh_token_exp=new_refresh_token_exp,
        )
    except core_exceptions.ConflictError:
        # A concurrent request presenting the same token recorded its rotation first and wins; this one
        # answers with the winner's replacement instead of rotating the session a second time.
        db.rollback()
        return _replay_rotation(client_type, session, refresh_token_value, token_user_id, token_manager, policy, db)

    # Edit session and store in database
    # Note: edit_session automatically increments rotation_count
    # and updates last_rotation_at
    sessions_integration.edit_session(
        session,
        ip_address,
        user_agent,
        new_refresh_token,
        password_hasher,
        new_refresh_token_exp,
        db,
        new_csrf_token=new_csrf_token,
    )
    db.commit()

    # Retire expired IdP tokens now and queue the refresh of those about to expire; the provider
    # calls run on a worker, never in this request.
    identity_providers_integration.request_idp_token_refresh(user.id, db)
    db.commit()

    # Token delivery based on client type (web cookie vs mobile body) is
    # centralised in build_token_response so login, /refresh, and
    # SSO token exchange share one delivery contract.
    return authentication_token_service.build_token_response(
        client_type,
        session_id,
        new_access_token,
        new_access_token_exp,
        new_refresh_token,
        new_refresh_token_exp,
        new_csrf_token,
    )
