"""Public route that finishes a sign-in whose password an administrator set."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

import core.dependencies as core_dependencies
import core.network as core_network
import core.openapi_contract as core_openapi_contract
import core.rate_limit as core_rate_limit
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.authentication.integration_service as authentication_integration
import modules.auth.authentication.schema as authentication_schema
import modules.auth.constants as auth_constants
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.known_devices.dependencies as known_devices_dependencies

router = APIRouter()


@router.post(
    "/password-change",
    response_model=authentication_schema.FinishedLoginRead,
    responses={
        200: {"headers": core_openapi_contract.NO_STORE_RESPONSE_HEADERS},
        401: {
            "description": "The password-change challenge is unknown, expired or used, or its account no longer "
            "needs to change the password."
        },
        403: {"description": "The account is no longer active."},
        422: {
            "description": "The new password does not meet the account's password policy; the challenge stays usable."
        },
    },
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def complete_password_change(
    response: Response,
    request: Request,
    change_request: authentication_schema.PasswordChangeLoginRequest,
    client_type: Annotated[auth_constants.ClientType, Depends(authentication_dependencies.get_client_type)],
    password_change_store: Annotated[
        authentication_integration.PendingPasswordChangeStore,
        Depends(authentication_integration.get_pending_password_change_store),
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
) -> authentication_schema.FinishedLoginRead:
    """Choose the new password that an administrator-set password requires, and finish signing in.

    Sign-in answers `next_step: password_change` when an administrator set the account's password; no session exists
    until this step succeeds. The challenge is valid for 10 minutes, and a password that fails the account's policy
    answers 422 and keeps it. The client type must be the one that signed in. The answer is the one the sign-in
    would have given: `tokens`, or `exchange` for a mobile client that sent a PKCE challenge at sign-in.
    """
    outcome = account_security_service.complete_password_change(
        core_network.get_ip_address(request),
        core_network.get_user_agent(request),
        change_request,
        client_type,
        password_change_store,
        password_hasher,
        token_manager,
        db,
        device_id=device_id,
    )
    return authentication_dependencies.deliver_auth_outcome(response, outcome)
