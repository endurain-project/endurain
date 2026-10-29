"""Public route that completes an SSO login by exchanging the PKCE verifier for tokens."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.authentication.schema as auth_schema
import modules.auth.authentication.service as authentication_service
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.dependencies as auth_dependencies
import modules.auth.mfa.dependencies as mfa_dependencies

router = APIRouter()


@router.post(
    "/session/{session_id}/tokens",
    response_model=auth_schema.TokenExchangeRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def exchange_tokens_for_session(
    session_id: auth_dependencies.AuthSessionId,
    request: Request,
    response: Response,
    token_exchange: auth_schema.TokenExchangeRequest,
    pending_mfa_store: Annotated[
        mfa_dependencies.PendingMFAStore,
        Depends(mfa_dependencies.get_pending_mfa_store),
    ],
    password_hasher: Annotated[
        credentials_integration.PasswordHasher,
        Depends(credentials_integration.get_password_hasher),
    ],
    token_manager: Annotated[
        access_tokens_integration.TokenManager,
        Depends(access_tokens_integration.get_token_manager),
    ],
    db: core_dependencies.DbSession,
) -> auth_schema.TokenExchangeRead:
    """Exchange a PKCE code verifier for the JWT tokens of an SSO session.

    After the identity-provider callback creates a session, the client proves it holds the PKCE code verifier and
    receives the tokens. The exchange succeeds once per session. An identity-provider session of an account with MFA
    enabled also needs ``mfa_code``; without it the answer is a ``403`` with the ``mfa-required`` problem type and the
    session stays usable.

    Args:
        session_id: Session created by the identity-provider callback.
        request: Incoming request, read for the ``X-Client-Type`` header.
        response: Response that receives the refresh cookie for web clients.
        token_exchange: Body carrying the PKCE code verifier and, when MFA applies, the MFA code.
        pending_mfa_store: Store for the MFA lockout and the TOTP replay guard.
        password_hasher: Hasher for the stored refresh token.
        token_manager: Token manager that signs the tokens.
        db: Database session.

    Returns:
        The access token and, per client type, the CSRF token or the refresh token.
    """
    outcome = authentication_service.exchange_tokens_for_session(
        session_id,
        token_exchange.code_verifier,
        token_exchange.mfa_code,
        request.headers.get("X-Client-Type"),
        pending_mfa_store,
        password_hasher,
        token_manager,
        db,
    )
    return authentication_dependencies.deliver_auth_outcome(response, outcome)
