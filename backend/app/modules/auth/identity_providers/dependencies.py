"""FastAPI dependencies for identity-provider workflows."""

from typing import Annotated

from fastapi import Depends

import core.config as core_config
import core.dependencies as core_dependencies
import modules.auth.identity_providers.authorization_service as authorization_service
import modules.auth.identity_providers.callback_service as callback_service
import modules.auth.identity_providers.oidc_client_service as oidc_client_service
import modules.auth.identity_providers.token_service as token_service


def get_oidc_client_service(state: core_dependencies.PlatformState) -> oidc_client_service.OidcClientService:
    """Build the identity-provider client for this request."""
    return oidc_client_service.OidcClientService(state, core_config.API_VERSION)


OidcClientService = Annotated[oidc_client_service.OidcClientService, Depends(get_oidc_client_service)]


def get_authorization_service(oidc: OidcClientService) -> authorization_service.AuthorizationService:
    """Build the service that starts SSO flows for this request."""
    return authorization_service.AuthorizationService(oidc, core_config.settings.ENDURAIN_HOST)


def get_callback_service(oidc: OidcClientService) -> callback_service.CallbackService:
    """Build the service that finishes SSO flows for this request."""
    return callback_service.CallbackService(
        oidc, token_service.IdpTokenService(oidc), core_config.settings.ENDURAIN_HOST
    )


AuthorizationService = Annotated[authorization_service.AuthorizationService, Depends(get_authorization_service)]
CallbackService = Annotated[callback_service.CallbackService, Depends(get_callback_service)]
