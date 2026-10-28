"""Identity operations consumed by the public authentication dependencies."""

import modules.auth.identity_service as identity_service_module
from modules.auth.principal import Principal


def resolve_from_access_token(
    access_token: str,
    identity_service: identity_service_module.IdentityService,
) -> Principal:
    """Resolve an access token through the authentication boundary."""
    return identity_service.resolve_from_access_token(access_token)
