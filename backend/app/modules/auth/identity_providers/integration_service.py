"""Identity-provider read operations exposed to auth peers."""

from sqlalchemy.orm import Session

import modules.auth.identity_provider_links.contracts as identity_links_contracts
import modules.auth.identity_provider_links.integration_service as identity_links_integration
import modules.auth.identity_provider_links.schema as identity_links_schema
import modules.auth.identity_providers.crud as identity_providers_crud
import modules.auth.identity_providers.schema as identity_providers_schema


def get_identity_providers_by_ids(
    idp_ids: list[int],
    db: Session,
) -> list[identity_providers_schema.IdentityProvider]:
    """Return identity providers matching a batch of IDs."""
    rows = identity_providers_crud.get_identity_providers_by_ids(idp_ids, db)
    return [identity_providers_schema.IdentityProvider.model_validate(row) for row in rows]


def enrich_user_identity_providers(
    idp_links: list[identity_links_contracts.IdentityLinkRead],
    user_id: int,
    db: Session,
) -> list[identity_links_schema.UsersIdentityProviderResponse]:
    """Add identity-provider display fields to a user's links."""
    if not idp_links:
        return []
    idps = get_identity_providers_by_ids([link.idp_id for link in idp_links], db)
    return identity_links_integration.enrich_user_identity_providers(idp_links, idps, user_id)
