"""Route that completes a sign-in by exchanging its session and PKCE verifier for tokens."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

import core.dependencies as core_dependencies
import core.network as core_network
import core.openapi_contract as core_openapi_contract
import core.rate_limit as core_rate_limit
import modules.auth.access_tokens.dependencies as access_tokens_dependencies
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.authentication.schema as auth_schema
import modules.auth.authentication.sso_exchange_service as authentication_sso_exchange_service
import modules.auth.constants as auth_constants
import modules.auth.dependencies as auth_dependencies
import modules.auth.known_devices.dependencies as known_devices_dependencies
import modules.auth.mfa.dependencies as mfa_dependencies

router = APIRouter()


@router.post(
    "/sessions/{session_id}/tokens",
    response_model=auth_schema.SessionExchangeRead,
    responses={
        200: {"headers": core_openapi_contract.NO_STORE_RESPONSE_HEADERS},
        400: {
            "description": "The verifier does not match, or the client type differs from the one that started the "
            "sign-in."
        },
        403: {"description": "The account is no longer active."},
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
    token_manager: access_tokens_dependencies.TokenManagerDep,
    db: core_dependencies.DbSession,
    device_id: known_devices_dependencies.DeviceId,
    state: core_dependencies.PlatformState,
) -> auth_schema.SessionExchangeRead:
    """Exchange a PKCE code verifier for the tokens of a session a sign-in created.

    A mobile password sign-in and an identity-provider callback create a session that holds no tokens. The client
    proves it holds the PKCE code verifier and receives the tokens: a web client the access token in the
    body and the refresh token as a cookie, a mobile client every token in the body. The exchange succeeds once per
    session, and only for the client type that started the sign-in. For an identity-provider session of an account
    with MFA enabled the answer is the ``mfa`` step instead, and the session stays unused: the client sends the
    account's code with ``mfa_challenge`` to ``/auth/mfa/verify``, which answers the session's tokens.
    """
    outcome = authentication_sso_exchange_service.exchange_tokens_for_session(
        session_id,
        token_exchange.code_verifier,
        client_type,
        core_network.get_ip_address(request),
        core_network.get_user_agent(request),
        pending_mfa_store,
        token_manager,
        db,
        device_id=device_id,
        state=state,
    )
    return authentication_dependencies.deliver_auth_outcome(response, outcome)
