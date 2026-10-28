"""FastAPI dependencies for identity-provider workflows."""

from typing import Annotated

from fastapi import Depends

import core.config as core_config
import core.dependencies as core_dependencies
import modules.auth.identity_providers.service as identity_provider_service


def get_identity_provider_service(
    state: core_dependencies.PlatformState,
) -> identity_provider_service.IdentityProviderService:
    """Build an identity-provider service for this request."""
    return identity_provider_service.IdentityProviderService(
        state,
        core_config.settings.ENDURAIN_HOST,
        core_config.API_VERSION,
    )


IdentityProviderService = Annotated[
    identity_provider_service.IdentityProviderService,
    Depends(get_identity_provider_service),
]
