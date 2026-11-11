"""FastAPI dependencies for identity-provider workflows."""

from typing import Annotated

from fastapi import Cookie, Depends, Form, Response
from fastapi.exceptions import RequestValidationError

import core.config as core_config
import core.dependencies as core_dependencies
import modules.auth.computation as auth_computation
import modules.auth.identity_providers.authorization_service as authorization_service
import modules.auth.identity_providers.backchannel_logout_service as backchannel_logout_service
import modules.auth.identity_providers.callback_service as callback_service
import modules.auth.identity_providers.oidc_client_service as oidc_client_service
import modules.auth.identity_providers.step_up_ticket_store as step_up_ticket_store
import modules.auth.identity_providers.token_service as token_service
import modules.auth.oauth_state.constants as oauth_state_constants

#: The cookie that binds a login, link or step-up to the browser that started it. Lax rather than Strict because the
#: callback, the one place that reads it, is a top-level navigation back from the provider.
#: A browser holds one at a time, so of two flows started together only the later can finish.
_BINDING_COOKIE_BASE_NAME = "endurain_idp_binding"
#: The name the browser sends the cookie back under, fixed when the server starts.
BINDING_COOKIE_NAME = auth_computation.host_cookie_name(_BINDING_COOKIE_BASE_NAME, core_config.settings.ENVIRONMENT)
#: The ``__Host-`` prefix requires ``Path=/``; the cookie is set without a ``Domain`` attribute.
BINDING_COOKIE_PATH = "/"


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


def get_backchannel_logout_service(
    oidc: OidcClientService, state: core_dependencies.PlatformState
) -> backchannel_logout_service.BackchannelLogoutService:
    """Build the service that handles a provider's back-channel logout for this request."""
    return backchannel_logout_service.BackchannelLogoutService(oidc, state)


AuthorizationService = Annotated[authorization_service.AuthorizationService, Depends(get_authorization_service)]
CallbackService = Annotated[callback_service.CallbackService, Depends(get_callback_service)]
BackchannelLogoutService = Annotated[
    backchannel_logout_service.BackchannelLogoutService, Depends(get_backchannel_logout_service)
]

#: Longest ``logout_token`` accepted. A logout token is a signed JWT of a few claims, well under 2 KB in practice.
LOGOUT_TOKEN_MAX_LENGTH = 16_384


def read_logout_token(
    logout_token: Annotated[
        str,
        Form(
            min_length=1,
            max_length=LOGOUT_TOKEN_MAX_LENGTH,
            description="The logout token: a JWT the provider signed (OpenID Connect Back-Channel Logout 1.0).",
        ),
    ],
) -> str:
    """Read the ``logout_token`` form field, refusing a NUL character in it.

    The NUL middleware reads urlencoded bodies but leaves multipart ones streaming, and FastAPI parses this form
    from multipart too, so the field is checked here.

    Args:
        logout_token: The posted field.

    Returns:
        The logout token.

    Raises:
        RequestValidationError: When the field holds a NUL (422).
    """
    if "\x00" in logout_token:
        raise RequestValidationError(
            [{"type": "value_error", "loc": ("body", "logout_token"), "msg": "NUL characters are not allowed"}]
        )
    return logout_token


#: The ``logout_token`` form field, with NUL characters refused.
LogoutToken = Annotated[str, Depends(read_logout_token)]

BrowserBinding = Annotated[str | None, Cookie(alias=BINDING_COOKIE_NAME, include_in_schema=False)]


def set_browser_binding_cookie(response: Response, browser_binding: str) -> None:
    """Keep a flow's browser binding in this browser until the flow's OAuth state expires.

    Args:
        response: The response that starts the login, link or step-up.
        browser_binding: The secret the callback requires.
    """
    response.set_cookie(
        key=auth_computation.host_cookie_name(_BINDING_COOKIE_BASE_NAME, core_config.settings.ENVIRONMENT),
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
        key=auth_computation.host_cookie_name(_BINDING_COOKIE_BASE_NAME, core_config.settings.ENVIRONMENT),
        path=BINDING_COOKIE_PATH,
        httponly=True,
        secure=auth_computation.secure_cookie(core_config.settings.ENVIRONMENT),
        samesite="lax",
    )
