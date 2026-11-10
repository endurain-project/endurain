"""Principal resolution and authentication operations."""

from __future__ import annotations

from datetime import UTC, datetime

import jasil.audit as jasil_audit
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.api_keys.integration_service as api_keys_integration
import modules.auth.authentication.audit_actions as authentication_audit_actions
import modules.auth.authentication.event_publishers as authentication_event_publishers
import modules.auth.sessions.integration_service as sessions_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema
from modules.auth.contracts import (
    AccessTokenCred,
    ApiKeyCred,
    OAuthCred,
    PasswordCred,
    Principal,
    SessionCookieCred,
)

logger = core_logger.get_logger(__name__)


def _build_principal(
    user: users_schema.UserRead,
    scopes: list[str],
    credential: (PasswordCred | AccessTokenCred | ApiKeyCred | SessionCookieCred | OAuthCred),
) -> Principal:
    """Build a ``Principal`` from a user read model.

    Args:
        user: The user read model.
        scopes: List of granted OAuth2 scope strings.
        credential: Typed credential variant.

    Returns:
        Principal: Frozen principal ready to cache on
            ``request.state``.
    """
    return Principal(
        user_id=user.id,
        username=user.username,
        email=user.email,
        is_active=bool(user.active),
        is_superuser=user.access_type == "admin",
        scopes=frozenset(scopes),
        credential=credential,
    )


def resolve_from_access_token(
    access_token: str,
    token_manager: access_tokens_integration.TokenManager,
    db: Session,
) -> Principal:
    """Validate a JWT access token and return a Principal.

    Args:
        access_token: The raw JWT string from the
            Authorization header.
        db: Database session.
        token_manager: Token manager that signs and validates the tokens.

    Returns:
        Principal: Resolved principal with an
            :class:`~auth.contracts.AccessTokenCred`.

    Raises:
        InvalidTokenError: If the token is expired, invalid, or its session
            or user no longer exists or is active, or the session passed its idle or absolute timeout.
    """
    token_manager.validate_access_expiration_logged(access_token)

    sub = token_manager.get_token_claim(access_token, "sub", access_tokens_integration.TokenType.ACCESS)
    if not isinstance(sub, str) or not sub.isascii() or not sub.isdecimal():
        logger.warning("Access token refused: malformed 'sub' claim")
        raise core_exceptions.InvalidTokenError("Invalid token: 'sub' claim must be a decimal string")

    sid = token_manager.get_token_claim(access_token, "sid", access_tokens_integration.TokenType.ACCESS)
    if not isinstance(sid, str):
        logger.warning("Access token refused: malformed 'sid' claim")
        raise core_exceptions.InvalidTokenError("Invalid token: 'sid' claim must be a string")

    # A token of a deleted or deactivated user is a dead credential, not a refusal the caller may learn about.
    user = users_integration.get_user(int(sub), db)
    if user is None or not user.active:
        logger.warning("Access token refused: its user is missing or inactive")
        raise core_exceptions.InvalidTokenError("User is no longer valid")

    # The token outlives its session unless it is checked: logging out, revoking sessions or a detected
    # refresh-token theft delete the session, and that must end the access token as well.
    session = sessions_integration.get_session_by_id_not_expired(sid, db)
    if session is None or session.user_id != user.id:
        logger.warning(
            "Access token refused: its session is no longer valid for user <user_id>",
            extra=core_logger.context(user_id=user.id),
        )
        raise core_exceptions.InvalidTokenError("Session is no longer valid")

    # The access token can outlive the idle window, and a policy change reaches sessions that already exist, so the
    # timeouts are checked against the current policy on every request, as a refresh does.
    try:
        sessions_integration.validate_session_timeout(session, server_settings_integration.get_session_policy(db))
    except core_exceptions.UnauthenticatedError as err:
        logger.warning(
            "Access token refused: its session timed out for user <user_id>",
            extra=core_logger.context(user_id=user.id),
        )
        raise core_exceptions.InvalidTokenError(err.detail) from err

    # A token holds the scopes it was issued with, and no more than the user's role holds now: a demotion takes
    # effect on the next request, and a token cannot name a scope its role lacks.
    return _build_principal(
        user,
        sorted(
            _token_scopes(token_manager, access_token)
            & set(access_tokens_integration.scopes_for_access_type(user.access_type))
        ),
        AccessTokenCred(session_id=sid),
    )


def _token_scopes(token_manager: access_tokens_integration.TokenManager, access_token: str) -> set[str]:
    """Return the scopes an access token carries.

    Args:
        access_token: The raw access token, already validated.
        token_manager: Token manager that reads the claims.

    Returns:
        The scopes of the space-separated ``scope`` claim.

    Raises:
        InvalidTokenError: If the claim is not a string.
    """
    scope = token_manager.get_token_claim(access_token, "scope", access_tokens_integration.TokenType.ACCESS)
    if not isinstance(scope, str):
        logger.warning("Access token refused: malformed 'scope' claim")
        raise core_exceptions.InvalidTokenError("Invalid token: 'scope' claim must be a string")
    return set(scope.split())


def _refuse_api_key(
    reason: authentication_audit_actions.ApiKeyRefusalReason,
    outcome: jasil_audit.Outcome,
    *,
    api_key_id: str | None = None,
    owner_id: int | None = None,
) -> None:
    """Record a refused API key on a transaction of its own, since the request answers with an error.

    The key, its prefix and its hash are never recorded.

    Args:
        reason: Why the key was refused.
        outcome: ``FAILURE`` for a key that is not valid, ``DENIED`` for a valid key that policy refuses.
        api_key_id: The id of the key, when it was found.
        owner_id: The owner of the key, when it was found.
    """
    target = (
        {}
        if api_key_id is None
        else {"target_type": "api_key", "target_id": api_key_id, "target_owner_id": str(owner_id)}
    )
    jasil_audit.record_detached(
        authentication_audit_actions.API_KEY_AUTHENTICATE,
        outcome=outcome,
        **target,
        details=authentication_audit_actions.ApiKeyRefusalDetails(reason=reason),
    )


def resolve_from_api_key(
    raw_key: str,
    endpoint: str,
    ip_address: str,
    db: Session,
) -> Principal:
    """Validate a raw API key and return a Principal.

    Args:
        raw_key: The plain-text API key from the
            ``X-API-Key`` header or ``?api_key=``
            query parameter.
        endpoint: Path of the request, recorded in the audit log.
        ip_address: Client address of the request, recorded in the audit log.
        db: Database session.

    Returns:
        Principal: Resolved principal with an
            :class:`~auth.contracts.ApiKeyCred`.

    Raises:
        UnauthenticatedError: If the key is not found,
            revoked, or expired.
        PermissionDeniedError: If the key's owner is inactive.

    Notes:
        Every refusal is audited as ``auth.api_key.authenticate``.
    """
    # The key is looked up by its SHA-256 digest, so a found row is the key and a missing one is refused.
    db_key = api_keys_integration.get_api_key_by_hash(api_keys_integration.hash_api_key(raw_key), db)
    if db_key is None:
        _refuse_api_key(authentication_audit_actions.ApiKeyRefusalReason.UNKNOWN_KEY, jasil_audit.Outcome.FAILURE)
        logger.warning(
            "API key refused: unknown key",
            extra=core_logger.context(endpoint=endpoint, ip=ip_address),
        )
        raise core_exceptions.UnauthenticatedError("Invalid API key", scheme="ApiKey")

    user = users_integration.require_user(db_key.user_id, db)
    try:
        users_integration.require_active_user(user)
    except core_exceptions.PermissionDeniedError:
        _refuse_api_key(
            authentication_audit_actions.ApiKeyRefusalReason.OWNER_INACTIVE,
            jasil_audit.Outcome.DENIED,
            api_key_id=db_key.id,
            owner_id=db_key.user_id,
        )
        raise

    if not db_key.is_active:
        _refuse_api_key(
            authentication_audit_actions.ApiKeyRefusalReason.REVOKED,
            jasil_audit.Outcome.FAILURE,
            api_key_id=db_key.id,
            owner_id=db_key.user_id,
        )
        logger.warning(
            "API key refused: key was revoked",
            extra=core_logger.context(
                key_prefix=db_key.key_prefix, user_id=db_key.user_id, endpoint=endpoint, ip=ip_address
            ),
        )
        raise core_exceptions.UnauthenticatedError("API key has been revoked", scheme="ApiKey")

    if datetime.now(UTC) > db_key.expires_at:
        _refuse_api_key(
            authentication_audit_actions.ApiKeyRefusalReason.EXPIRED,
            jasil_audit.Outcome.FAILURE,
            api_key_id=db_key.id,
            owner_id=db_key.user_id,
        )
        logger.warning(
            "API key refused: key has expired",
            extra=core_logger.context(
                key_prefix=db_key.key_prefix, user_id=db_key.user_id, endpoint=endpoint, ip=ip_address
            ),
        )
        raise core_exceptions.UnauthenticatedError("API key has expired", scheme="ApiKey")

    authentication_event_publishers.publish_api_key_used(db_key.id, db)

    logger.debug(
        "API key authenticated",
        extra=core_logger.context(
            key_prefix=db_key.key_prefix,
            user_id=db_key.user_id,
            endpoint=endpoint,
            ip=ip_address,
        ),
    )

    return _build_principal(
        user,
        db_key.scopes,
        ApiKeyCred(
            api_key_id=db_key.id,
            key_prefix=db_key.key_prefix,
        ),
    )
