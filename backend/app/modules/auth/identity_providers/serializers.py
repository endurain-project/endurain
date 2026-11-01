"""Convert identity-provider rows into internal and client contracts."""

import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.auth.identity_providers.models as identity_provider_models
import modules.auth.identity_providers.schema as identity_provider_schema


def to_state(row: identity_provider_models.IdentityProvider) -> identity_provider_contracts.IdentityProviderState:
    """Return the internal stored state for an identity-provider row."""
    return identity_provider_contracts.IdentityProviderState.model_validate(row)


def to_read_schema(
    state: identity_provider_contracts.IdentityProviderState,
) -> identity_provider_schema.IdentityProviderRead:
    """Return the client-facing provider representation."""
    return identity_provider_schema.IdentityProviderRead.model_validate(state)
