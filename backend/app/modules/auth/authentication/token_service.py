"""Access token minting and the token response shared by login, refresh and SSO exchange."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import core.logger as core_logger
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.schema as auth_schema
import modules.server_settings.contracts as server_settings_contracts
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


def create_tokens(
    user: users_schema.UsersRead,
    token_manager: access_tokens_integration.TokenManager,
    policy: server_settings_contracts.SessionPolicy,
    session_id: str | None = None,
) -> tuple[str, datetime, str, datetime, str, str]:
    """Generates session tokens for a user, including access token, refresh token, and CSRF token.

    Args:
        user (users_schema.UsersRead): The user object for whom the tokens are being created.
        token_manager (access_tokens_integration.TokenManager): The token manager responsible for token creation.
        policy (server_settings_contracts.SessionPolicy): The token lifetimes to apply.
        session_id (str | None, optional): An optional session ID. If not provided, a new unique session ID is generated.

    Returns:
        tuple[str, datetime, str, datetime, str, str]:
            A tuple containing:
                - session_id (str): The session identifier.
                - access_token_exp (datetime): Expiration datetime of the access token.
                - access_token (str): The access token string.
                - refresh_token_exp (datetime): Expiration datetime of the refresh token.
                - refresh_token (str): The refresh token string.
                - csrf_token (str): The CSRF token string.
    """
    if session_id is None:
        # Generate a unique session ID
        session_id = str(uuid4())

    # Create the access, refresh tokens and csrf token
    access_token_exp, access_token = token_manager.create_token(
        session_id, user, access_tokens_integration.TokenType.ACCESS, policy.access_token_ttl
    )

    refresh_token_exp, refresh_token = token_manager.create_token(
        session_id, user, access_tokens_integration.TokenType.REFRESH, policy.refresh_token_ttl
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
    user: users_schema.UsersRead,
    token_manager: access_tokens_integration.TokenManager,
    session_id: str,
    policy: server_settings_contracts.SessionPolicy,
) -> tuple[datetime, str]:
    """Mint a single fresh access token for an existing session.

    Used by the in-grace refresh replay path, which keeps the
    existing (replayed) refresh token but still needs to hand the
    client a new, full-lifetime access token.

    Args:
        user: The user the token is issued for.
        token_manager: Token manager responsible for token creation.
        session_id: Existing session identifier to bind the token to.
        policy: The token lifetimes to apply.

    Returns:
        Tuple of (access_token_exp, access_token).
    """
    return token_manager.create_token(
        session_id, user, access_tokens_integration.TokenType.ACCESS, policy.access_token_ttl
    )


def build_token_response(
    client_type: str,
    session_id: str,
    access_token: str,
    access_token_exp: datetime,
    refresh_token: str,
    refresh_token_exp: datetime,
    csrf_token: str,
) -> auth_schema.AuthOutcome[auth_schema.TokenRead]:
    """Build the OAuth 2.1 token-response body for login and refresh.

    Single source of truth for token delivery, shared by the password
    login, SSO login, and ``/refresh`` flows so they cannot drift:

    - Web clients receive the refresh token as an ``HttpOnly`` cookie
      (set by the router from the returned outcome) and the CSRF token
      in the body.
    - Mobile clients receive the refresh token in the body and no CSRF
      token.

    ``expires_in`` / ``refresh_token_expires_in`` are seconds-until-expiry
    per RFC 6749 §5.1.

    Args:
        client_type: ``"web"`` or any other value (treated as mobile).
        session_id: Session identifier.
        access_token: Newly minted access token.
        access_token_exp: Access-token expiry datetime.
        refresh_token: Newly minted refresh token.
        refresh_token_exp: Refresh-token expiry datetime.
        csrf_token: CSRF token, returned only to web clients.

    Returns:
        The response body and, for a web client, the refresh cookie the router sets.
    """
    now = datetime.now(UTC)
    expires_in = int((access_token_exp - now).total_seconds())
    refresh_token_expires_in = int((refresh_token_exp - now).total_seconds())

    if client_type == "web":
        # Web: Refresh token as httpOnly cookie (XSS protection); CSRF
        # token in body for in-memory storage. The router sets the cookie
        # through deliver_auth_outcome so login, /refresh, and SSO token
        # exchange stay in lockstep.
        return auth_schema.AuthOutcome(
            auth_schema.TokenWebRead(
                session_id=session_id,
                access_token=access_token,
                csrf_token=csrf_token,
                expires_in=expires_in,
                refresh_token_expires_in=refresh_token_expires_in,
            ),
            auth_schema.RefreshCookie(refresh_token, refresh_token_exp),
        )

    # Mobile: All tokens in JSON body for secure platform storage.
    return auth_schema.AuthOutcome(
        auth_schema.TokenMobileRead(
            session_id=session_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            refresh_token_expires_in=refresh_token_expires_in,
        )
    )
