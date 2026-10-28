"""Principal resolution and authentication operations."""

from __future__ import annotations

import hmac
from datetime import UTC, datetime

from fastapi import HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.logger as core_logger
import core.network as core_network
import modules.auth.access_tokens.integration_service as auth_token_manager
import modules.auth.api_keys.integration_service as auth_api_keys_integration
import modules.auth.authentication.service as authentication_service
import modules.auth.credentials.integration_service as auth_password_hasher
import modules.auth.sessions.integration_service as auth_sessions_crud
import modules.server_settings.contracts as server_settings_contracts
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
    user: object,
    scopes: list[str],
    credential: (PasswordCred | AccessTokenCred | ApiKeyCred | SessionCookieCred | OAuthCred),
) -> Principal:
    """Build a ``Principal`` from an ORM user row.

    Args:
        user: SQLAlchemy ``Users`` model instance.
        scopes: List of granted OAuth2 scope strings.
        credential: Typed credential variant.

    Returns:
        Principal: Frozen principal ready to cache on
            ``request.state``.
    """
    return Principal(
        user_id=user.id,  # type: ignore[attr-defined]
        username=user.username,  # type: ignore[attr-defined]
        email=user.email,  # type: ignore[attr-defined]
        is_active=bool(user.active),  # type: ignore[attr-defined]
        is_superuser=(
            user.access_type == "admin"  # type: ignore[attr-defined]
        ),
        scopes=frozenset(scopes),
        credential=credential,
    )


def authenticate_password(
    username: str,
    password: str,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
) -> Principal:
    """Verify username/password and return a Principal.

    Args:
        username: The username supplied by the caller.
        password: The plaintext password to verify.

    Returns:
        Principal: Resolved principal with a
            :class:`~auth.contracts.PasswordCred`.

    Raises:
        HTTPException: 401 if the credentials are
            invalid or the account does not exist.
    """
    user = authentication_service.authenticate_user(
        username,
        password,
        password_hasher,
        db,
    )
    # Scopes are determined by the token-issuing step;
    # at password-auth time we return an empty set so
    # callers know authentication succeeded but must
    # call issue_token_pair to get scoped tokens.
    return _build_principal(user, [], PasswordCred(username=username))


def resolve_from_access_token(
    access_token: str,
    token_manager: auth_token_manager.TokenManager,
    db: Session,
) -> Principal:
    """Validate a JWT access token and return a Principal.

    Args:
        access_token: The raw JWT string from the
            Authorization header.

    Returns:
        Principal: Resolved principal with an
            :class:`~auth.contracts.AccessTokenCred`.

    Raises:
        HTTPException: 401 if the token is expired,
            invalid, or the user is not found.
    """
    token_manager.validate_access_expiration_logged(access_token)

    sub = token_manager.get_token_claim(access_token, "sub")
    if not isinstance(sub, str) or not sub.isascii() or not sub.isdecimal():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: 'sub' claim must be a decimal string",
        )

    scope = token_manager.get_token_claim(access_token, "scope")
    if not isinstance(scope, list):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: 'scope' claim must be a list",
        )

    sid = token_manager.get_token_claim(access_token, "sid")
    if not isinstance(sid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=("Invalid token: 'sid' claim must be a string"),
        )

    user = users_integration.require_user(int(sub), db)
    users_integration.require_active_user(user)

    return _build_principal(
        user,
        scope,
        AccessTokenCred(session_id=sid),
    )


def resolve_from_api_key(
    raw_key: str,
    request: Request,
    db: Session,
) -> Principal:
    """Validate a raw API key and return a Principal.

    Args:
        raw_key: The plain-text API key from the
            ``X-API-Key`` header or ``?api_key=``
            query parameter.
        request: The current HTTP request (used for
            audit logging).

    Returns:
        Principal: Resolved principal with an
            :class:`~auth.contracts.ApiKeyCred`.

    Raises:
        HTTPException: 401 if the key is not found,
            revoked, or expired.
    """
    computed_hash = auth_api_keys_integration.hash_api_key(raw_key)
    db_key = auth_api_keys_integration.get_api_key_by_hash(computed_hash, db)

    # Constant-time comparison prevents timing attacks
    # even when the key is not found.
    stored_hash = db_key.key_hash if db_key else ("0" * 64)
    if not hmac.compare_digest(stored_hash, computed_hash):
        db_key = None

    if db_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    user = users_integration.require_user(db_key.user_id, db)
    users_integration.require_active_user(user)

    if not db_key.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has been revoked",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if db_key.expires_at is not None and datetime.now(UTC) > db_key.expires_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Best-effort last_used_at update; never fails the request.
    try:
        auth_api_keys_integration.update_last_used(db_key.id, db)
    except SQLAlchemyError as err:
        logger.warning(f"Failed to update last_used_at for API key {db_key.id}: {err}", exc_info=err)

    logger.info(
        "API key authenticated",
        extra=core_logger.context(
            key_prefix=db_key.key_prefix,
            user_id=db_key.user_id,
            endpoint=request.url.path,
            ip=core_network.get_ip_address(request),
        ),
    )

    scopes = auth_api_keys_integration.json_to_scopes(db_key.scopes)
    return _build_principal(
        user,
        scopes,
        ApiKeyCred(
            api_key_id=db_key.id,
            key_prefix=db_key.key_prefix,
        ),
    )


def resolve_from_session_cookie(
    session_id: str,
    db: Session,
) -> Principal:
    """Validate a session ID and return a Principal.

    Args:
        session_id: The session identifier from the
            cookie or token ``sid`` claim.

    Returns:
        Principal: Resolved principal with a
            :class:`~auth.contracts.SessionCookieCred`.

    Raises:
        HTTPException: 401 if the session is not
            found or has expired.
    """
    db_session = auth_sessions_crud.get_session_by_id_not_expired(session_id, db)
    if db_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session not found or expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = users_integration.require_user(db_session.user_id, db)
    users_integration.require_active_user(user)

    return _build_principal(
        user,
        [],
        SessionCookieCred(session_id=session_id),
    )


def issue_token_pair(
    user: users_schema.UsersRead,
    policy: server_settings_contracts.SessionPolicy,
    token_manager: auth_token_manager.TokenManager,
    session_id: str | None = None,
) -> tuple[str, datetime, str, datetime, str, str]:
    """Issue an access/refresh token pair for a user.

    Args:
        user: The validated user object.
        policy: The token lifetimes to apply.
        session_id: Optional existing session
            identifier; a new UUID is generated
            when ``None``.

    Returns:
        tuple: ``(session_id, access_token_exp,
            access_token, refresh_token_exp,
            refresh_token, csrf_token)``.
    """
    return authentication_service.create_tokens(user, token_manager, policy, session_id)


def revoke_session(
    session_id: str,
    user_id: int,
    db: Session,
) -> None:
    """Revoke and delete a session.

    Args:
        session_id: The session to revoke.
        user_id: Owner of the session (used to
            prevent cross-user revocations).

    Raises:
        HTTPException: 404 if the session is not
            found for this user.
    """
    auth_sessions_crud.delete_session(session_id, user_id, db)
