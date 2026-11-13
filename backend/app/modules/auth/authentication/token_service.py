"""Access token minting and the token response shared by login, refresh and SSO exchange."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import core.logger as core_logger
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.schema as auth_schema
import modules.auth.constants as auth_constants
import modules.server_settings.contracts as server_settings_contracts
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


def create_tokens(
    user: users_schema.UserRead,
    client_type: auth_constants.ClientType,
    token_manager: access_tokens_integration.TokenManager,
    policy: server_settings_contracts.SessionPolicy,
    session_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, datetime, str, datetime, str, str]:
    """Generates session tokens for a user, including access token, refresh token, and CSRF token.

    Args:
        user (users_schema.UserRead): The user object for whom the tokens are being created.
        client_type: The client type of the session, carried by both tokens as ``client_id``.
        token_manager (access_tokens_integration.TokenManager): The token manager responsible for token creation.
        policy (server_settings_contracts.SessionPolicy): The token lifetimes to apply.
        session_id (uuid.UUID | None, optional): An optional session ID. If not provided, a new unique session ID is generated.

    Returns:
        tuple[uuid.UUID, datetime, str, datetime, str, str]:
            A tuple containing:
                - session_id (uuid.UUID): The session identifier.
                - access_token_exp (datetime): Expiration datetime of the access token.
                - access_token (str): The access token string.
                - refresh_token_exp (datetime): Expiration datetime of the refresh token.
                - refresh_token (str): The refresh token string.
                - csrf_token (str): The CSRF token string.
    """
    if session_id is None:
        # Generate a unique session ID
        session_id = uuid.uuid4()

    # Create the access, refresh tokens and csrf token
    access_token_exp, access_token = token_manager.create_token(
        session_id, user, client_type, access_tokens_integration.TokenType.ACCESS, policy.access_token_ttl
    )

    refresh_token_exp, refresh_token = token_manager.create_token(
        session_id, user, client_type, access_tokens_integration.TokenType.REFRESH, policy.refresh_token_ttl
    )

    csrf_token = token_manager.create_csrf_token()

    return (
        session_id,
        access_token_exp,
        access_token,
        refresh_token_exp,
        refresh_token,
        csrf_token,
    )


def mint_access_token(
    user: users_schema.UserRead,
    client_type: auth_constants.ClientType,
    token_manager: access_tokens_integration.TokenManager,
    session_id: uuid.UUID,
    policy: server_settings_contracts.SessionPolicy,
) -> tuple[datetime, str]:
    """Mint a single fresh access token for an existing session.

    Used by the in-grace refresh replay path, which keeps the
    existing (replayed) refresh token but still needs to hand the
    client a new, full-lifetime access token.

    Args:
        user: The user the token is issued for.
        client_type: The client type of the session, carried by the token as ``client_id``.
        token_manager: Token manager responsible for token creation.
        session_id: Existing session identifier to bind the token to.
        policy: The token lifetimes to apply.

    Returns:
        Tuple of (access_token_exp, access_token).
    """
    return token_manager.create_token(
        session_id, user, client_type, access_tokens_integration.TokenType.ACCESS, policy.access_token_ttl
    )


def cap_refresh_expiry(refresh_token_exp: datetime, session_expires_at: datetime) -> datetime:
    """Return when the client must treat the refresh token as expired.

    The session ends at its own expiry, which the absolute session timeout can put before the refresh
    token's, so the client is told whichever comes first.

    Args:
        refresh_token_exp: Expiry of the refresh token.
        session_expires_at: Expiry of the session the token belongs to.

    Returns:
        The earlier of the two.
    """
    return min(refresh_token_exp, session_expires_at)


def build_web_token_response(
    session_id: uuid.UUID,
    access_token: str,
    access_token_exp: datetime,
    refresh_token: str,
    refresh_token_exp: datetime,
    session_expires_at: datetime,
    csrf_token: str,
) -> auth_schema.AuthOutcome[auth_schema.TokenWebRead]:
    """Build the token body of a web client: the refresh token travels in an ``HttpOnly`` cookie.

    The CSRF token is in the body for in-memory storage. The router sets the cookie through
    ``deliver_auth_outcome``, so login, ``/auth/refresh`` and the token exchange stay in lockstep.
    ``expires_in`` and ``refresh_token_expires_in`` are seconds until expiry per RFC 6749 section 5.1; the refresh
    lifetime and the cookie expiry are those of the session when it ends before the refresh token does.

    Args:
        session_id: Session identifier.
        access_token: Newly minted access token.
        access_token_exp: Access-token expiry datetime.
        refresh_token: Newly minted refresh token.
        refresh_token_exp: Refresh-token expiry datetime.
        session_expires_at: Expiry of the session the refresh token belongs to.
        csrf_token: CSRF token for the body.

    Returns:
        The response body and the refresh cookie the router sets.
    """
    now = datetime.now(UTC)
    refresh_token_exp = cap_refresh_expiry(refresh_token_exp, session_expires_at)
    return auth_schema.AuthOutcome(
        auth_schema.TokenWebRead(
            next_step="tokens",
            session_id=session_id,
            access_token=access_token,
            csrf_token=csrf_token,
            expires_in=int((access_token_exp - now).total_seconds()),
            refresh_token_expires_in=int((refresh_token_exp - now).total_seconds()),
        ),
        auth_schema.RefreshCookie(refresh_token, refresh_token_exp),
    )


def build_mobile_token_response(
    session_id: uuid.UUID,
    access_token: str,
    access_token_exp: datetime,
    refresh_token: str,
    refresh_token_exp: datetime,
    session_expires_at: datetime,
    device_id: str | None = None,
) -> auth_schema.AuthOutcome[auth_schema.TokenMobileRead]:
    """Build the token body of a mobile client: every token is in the JSON body, for secure platform storage.

    Args:
        session_id: Session identifier.
        access_token: Newly minted access token.
        access_token_exp: Access-token expiry datetime.
        refresh_token: Newly minted refresh token.
        refresh_token_exp: Refresh-token expiry datetime.
        session_expires_at: Expiry of the session the refresh token belongs to.
        device_id: The device id the app keeps, when the exchange issued one.

    Returns:
        The response body.
    """
    now = datetime.now(UTC)
    refresh_token_exp = cap_refresh_expiry(refresh_token_exp, session_expires_at)
    return auth_schema.AuthOutcome(
        auth_schema.TokenMobileRead(
            next_step="tokens",
            session_id=session_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int((access_token_exp - now).total_seconds()),
            refresh_token_expires_in=int((refresh_token_exp - now).total_seconds()),
            device_id=device_id,
        )
    )


def build_token_response(
    client_type: auth_constants.ClientType,
    session_id: uuid.UUID,
    access_token: str,
    access_token_exp: datetime,
    refresh_token: str,
    refresh_token_exp: datetime,
    session_expires_at: datetime,
    csrf_token: str,
) -> auth_schema.AuthOutcome[auth_schema.TokenRead]:
    """Build the token body of ``/auth/refresh`` for a web or a mobile client.

    Args:
        client_type: The client type.
        session_id: Session identifier.
        access_token: Newly minted access token.
        access_token_exp: Access-token expiry datetime.
        refresh_token: Newly minted refresh token.
        refresh_token_exp: Refresh-token expiry datetime.
        session_expires_at: Expiry of the session the refresh token belongs to.
        csrf_token: CSRF token, returned only to web clients.

    Returns:
        The response body and, for a web client, the refresh cookie the router sets.
    """
    if client_type == auth_constants.ClientType.WEB:
        web = build_web_token_response(
            session_id, access_token, access_token_exp, refresh_token, refresh_token_exp, session_expires_at, csrf_token
        )
        return auth_schema.AuthOutcome(web.body, web.refresh_cookie)
    mobile = build_mobile_token_response(
        session_id, access_token, access_token_exp, refresh_token, refresh_token_exp, session_expires_at
    )
    return auth_schema.AuthOutcome(mobile.body)
