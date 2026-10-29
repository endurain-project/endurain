"""Identity-provider operations exposed to auth peers."""

from collections.abc import Callable

import jasil.runtime as platform_runtime
from sqlalchemy.orm import Session

import core.config as core_config
import modules.auth.identity_provider_links.contracts as identity_links_contracts
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_provider_links.schema as identity_links_schema
import modules.auth.identity_providers.contracts as identity_providers_contracts
import modules.auth.identity_providers.crud as identity_providers_crud
import modules.auth.identity_providers.service as identity_providers_service


def _service() -> identity_providers_service.IdentityProviderService:
    """Resolve runtime state and build an IdP service at this entrypoint."""
    return identity_providers_service.IdentityProviderService(
        platform_runtime.get_state(), core_config.settings.ENDURAIN_HOST, core_config.API_VERSION
    )


def get_identity_provider(idp_id: int, db: Session) -> identity_providers_contracts.IdentityProviderState | None:
    """Return a provider's stored state."""
    return identity_providers_crud.get_identity_provider(idp_id, db)


def enrich_user_identity_providers(
    idp_links: list[identity_links_contracts.IdentityLinkRead],
    user_id: int,
    db: Session,
) -> list[identity_links_schema.IdentityProviderLinkRead]:
    """Add identity-provider display fields to a user's links."""
    if not idp_links:
        return []
    idps = identity_providers_crud.get_identity_providers_by_ids([link.idp_id for link in idp_links], db)
    return identity_provider_links_integration.enrich_user_identity_providers(idp_links, idps, user_id)


def start_browser_link(
    link_token: str,
    idp_id: int,
    redirect: str | None,
    client_ip: str | None,
    claim_link_token: Callable[..., int],
    db: Session,
) -> str:
    """Claim a browser link token and prepare its identity-provider redirect."""
    return _service().start_browser_link(
        link_token,
        idp_id,
        redirect,
        client_ip,
        claim_link_token,
        core_config.settings.ALLOWED_REDIRECT_SCHEMES,
        db,
    )


def request_idp_token_refresh(user_id: int, db: Session) -> None:
    """Clear the user's retired IdP tokens now and queue the refresh of those expiring, with the caller's commit."""
    _service().request_idp_token_refresh(user_id, db)


def clear_all_idp_tokens(user_id: int, db: Session, revoke_at_idp: bool = False) -> None:
    """Clear all locally stored IdP refresh tokens, optionally revoking them remotely."""
    _service().clear_all_idp_tokens(user_id, db, revoke_at_idp)
