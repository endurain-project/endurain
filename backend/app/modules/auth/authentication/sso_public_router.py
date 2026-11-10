"""Route that completes a sign-in by exchanging its session and PKCE verifier for tokens."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

import core.dependencies as core_dependencies
import core.network as core_network
import core.openapi_contract as core_openapi_contract
import core.rate_limit as core_rate_limit
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.authentication.schema as auth_schema
import modules.auth.authentication.sso_exchange_service as authentication_sso_exchange_service
import modules.auth.constants as auth_constants
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.dependencies as auth_dependencies
import modules.auth.known_devices.dependencies as known_devices_dependencies
import modules.auth.mfa.dependencies as mfa_dependencies

router = APIRouter()


@router.post(
    "/sessions/{session_id}/tokens",
    response_model=auth_schema.TokenWebRead | auth_schema.TokenMobileRead,
    responses={
        200: {"headers": core_openapi_contract.NO_STORE_RESPONSE_HEADERS},
        400: {
            "description": "The verifier does not match, the client type differs from the one that started the "
            "sign-in, or the `mfa_code` is wrong."
        },
        403: {
            "description": "The account is no longer active, or it has MFA enabled and the request carried no "
            "`mfa_code` (the `mfa-required` problem type); the session stays usable."
        },
    },
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def exchange_tokens_for_session(
    session_id: auth_dependencies.AuthSessionId,
    request: Request,
    response: Response,
    client_type: Annotated[auth_constants.ClientType, Depends(authentication_dependencies.get_client_type)],
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
    device_id: known_devices_dependencies.DeviceId,
) -> auth_schema.TokenRead:
    """Exchange a PKCE code verifier for the tokens of a session a sign-in created.

    A mobile password sign-in and an identity-provider callback create a session that holds no tokens. The client
    proves it holds the PKCE code verifier and receives the tokens: a web client the access and CSRF tokens in the
    body and the refresh token as a cookie, a mobile client every token in the body. The exchange succeeds once per
    session, and only for the client type that started the sign-in. An identity-provider session of an account with
    MFA enabled also needs ``mfa_code``; without it the answer is a ``403`` with the ``mfa-required`` problem type
    and the session stays usable.

    Args:
        session_id: Session created by the sign-in.
        request: Incoming request, read for the client address and the user agent.
        response: Response that receives the refresh and device cookies for web clients.
        client_type: The ``X-Client-Type`` header; it must be the client type that started the sign-in.
        token_exchange: Body carrying the PKCE code verifier and, when MFA applies, the MFA code.
        pending_mfa_store: Store for the MFA lockout and the TOTP replay guard.
        password_hasher: Hasher for the stored refresh token.
        token_manager: Token manager that signs the tokens.
        db: Database session.
        device_id: Device id from the browser's device cookie or the mobile app's X-Device-Id header, or None when
            the client sent no valid one.

    Returns:
        The access token and, per client type, the CSRF token or the refresh token.
    """
    outcome = authentication_sso_exchange_service.exchange_tokens_for_session(
        session_id,
        token_exchange.code_verifier,
        token_exchange.mfa_code,
        client_type,
        core_network.get_ip_address(request),
        core_network.get_user_agent(request),
        pending_mfa_store,
        password_hasher,
        token_manager,
        db,
        device_id=device_id,
    )
    return authentication_dependencies.deliver_auth_outcome(response, outcome)
