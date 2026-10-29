"""FastAPI dependencies for identity-provider workflows."""

from typing import Annotated

from fastapi import Cookie, Depends, Response

import core.config as core_config
import core.dependencies as core_dependencies
import modules.auth.computation as auth_computation
import modules.auth.identity_providers.authorization_service as authorization_service
import modules.auth.identity_providers.callback_service as callback_service
import modules.auth.identity_providers.oidc_client_service as oidc_client_service
import modules.auth.identity_providers.step_up_ticket_store as step_up_ticket_store
import modules.auth.identity_providers.token_service as token_service
import modules.auth.oauth_state.constants as oauth_state_constants

#: The cookie that binds a link or step-up to the browser that started it. Scoped to the callback, the one place
#: that reads it, and Lax rather than Strict because the callback is a top-level navigation back from the provider.
#: A browser holds one at a time, so of two flows started together only the later can finish.
BINDING_COOKIE_NAME = "endurain_idp_binding"
BINDING_COOKIE_PATH = core_config.ROOT_PATH + "/public/idp/callback"


def get_oidc_client_service(state: core_dependencies.PlatformState) -> oidc_client_service.OidcClientService:
    """Build the identity-provider client for this request."""
    return oidc_client_service.OidcClientService(state, core_config.API_VERSION)


OidcClientService = Annotated[oidc_client_service.OidcClientService, Depends(get_oidc_client_service)]


def get_authorization_service(oidc: OidcClientService) -> authorization_service.AuthorizationService:
    """Build the service that starts SSO flows for this request."""
    return authorization_service.AuthorizationService(oidc, core_config.settings.ENDURAIN_HOST)


def get_callback_service(
    oidc: OidcClientService, state: core_dependencies.PlatformState
) -> callback_service.CallbackService:
    """Build the service that finishes SSO flows for this request."""
    return callback_service.CallbackService(
        oidc,
        token_service.IdpTokenService(oidc),
        step_up_ticket_store.StepUpTicketStore(state),
        core_config.settings.ENDURAIN_HOST,
    )


AuthorizationService = Annotated[authorization_service.AuthorizationService, Depends(get_authorization_service)]
CallbackService = Annotated[callback_service.CallbackService, Depends(get_callback_service)]

BrowserBinding = Annotated[str | None, Cookie(alias=BINDING_COOKIE_NAME, include_in_schema=False)]


def set_browser_binding_cookie(response: Response, browser_binding: str) -> None:
    """Keep a flow's browser binding in this browser until the flow's OAuth state expires.

    Args:
        response: The response that starts the link or step-up.
        browser_binding: The secret the callback requires.
    """
    response.set_cookie(
        key=BINDING_COOKIE_NAME,
        value=browser_binding,
        max_age=oauth_state_constants.STATE_TTL_SECONDS,
        path=BINDING_COOKIE_PATH,
        httponly=True,
        secure=auth_computation.secure_cookie(core_config.settings.ENVIRONMENT),
        samesite="lax",
    )


def clear_browser_binding_cookie(response: Response) -> None:
    """Drop a flow's browser binding once its callback has been answered.

    Args:
        response: The callback's response.
    """
    response.delete_cookie(
        key=BINDING_COOKIE_NAME,
        path=BINDING_COOKIE_PATH,
        httponly=True,
        secure=auth_computation.secure_cookie(core_config.settings.ENVIRONMENT),
        samesite="lax",
    )
