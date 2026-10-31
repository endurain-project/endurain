"""Identity-provider link DTO conversion."""

import modules.auth.identity_provider_links.contracts as identity_link_contracts
import modules.auth.identity_provider_links.models as identity_link_models


def to_read_schema(row: identity_link_models.IdentityLink) -> identity_link_contracts.IdentityLinkRead:
    """Convert an identity-link row to its internal DTO."""
    return identity_link_contracts.IdentityLinkRead.model_validate(row)
