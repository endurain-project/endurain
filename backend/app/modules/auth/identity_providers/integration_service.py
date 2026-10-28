"""Identity-provider operations exposed to auth peers."""

from collections.abc import Callable

import jasil.runtime as platform_runtime
from fastapi import Request
from sqlalchemy.orm import Session

import core.config as core_config
import core.network as core_network
import modules.auth.identity_provider_links.contracts as identity_links_contracts
import modules.auth.identity_provider_links.integration_service as identity_links_integration
import modules.auth.identity_provider_links.schema as identity_links_schema
import modules.auth.identity_providers.contracts as identity_providers_contracts
import modules.auth.identity_providers.crud as identity_providers_crud
import modules.auth.identity_providers.service as identity_providers_service
import modules.auth.oauth_state.integration_service as oauth_state_integration


def _service() -> identity_providers_service.IdentityProviderService:
    """Resolve runtime state and build an IdP service at this entrypoint."""
    return identity_providers_service.IdentityProviderService(
        platform_runtime.get_state(), core_config.settings.ENDURAIN_HOST, core_config.API_VERSION
    )


def get_identity_provider(idp_id: int, db: Session) -> identity_providers_contracts.IdentityProviderState | None:
    """Return a provider's stored state."""
    return identity_providers_crud.get_identity_provider(idp_id, db)


def get_identity_providers_by_ids(
    idp_ids: list[int], db: Session
) -> list[identity_providers_contracts.IdentityProviderState]:
    """Return provider states matching a batch of IDs."""
    return identity_providers_crud.get_identity_providers_by_ids(idp_ids, db)


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


def create_link_oauth_state(
    db: Session,
    *,
    state_id: str,
    idp_id: int,
    nonce: str,
    client_type: str,
    ip_address: str | None,
    user_id: int,
    redirect_path: str | None,
) -> None:
    """Stage OAuth state for a browser IdP-link flow."""
    oauth_state_integration.create_oauth_state(
        db=db,
        state_id=state_id,
        idp_id=idp_id,
        nonce=nonce,
        client_type=client_type,
        ip_address=ip_address,
        user_id=user_id,
        redirect_path=redirect_path,
    )


def initiate_link(
    idp_id: int,
    request,
    user_id: int,
    db: Session,
    *,
    oauth_state_id: str,
) -> str:
    """Build an authorization URL for an existing user's link flow."""
    idp = get_identity_provider(idp_id, db)
    if idp is None or not idp.enabled:
        import core.exceptions as core_exceptions

        raise core_exceptions.NotFoundError("Identity provider not found or disabled")
    return _service().initiate_link(idp, user_id, db, oauth_state_id=oauth_state_id)


def start_browser_link(
    link_token: str,
    idp_id: int,
    redirect: str | None,
    request: Request,
    claim_link_token: Callable[..., int],
    db: Session,
) -> str:
    """Claim a browser link token and prepare its identity-provider redirect."""
    client_ip = core_network.get_ip_address(request)
    return _service().start_browser_link(
        link_token,
        idp_id,
        redirect,
        client_ip,
        claim_link_token,
        db,
        core_config.settings.ALLOWED_REDIRECT_SCHEMES,
    )


def refresh_idp_tokens_if_needed(user_id: int, db: Session) -> None:
    """Refresh or clear the user's stored IdP tokens when policy requires it."""
    _service().refresh_idp_tokens_if_needed(user_id, db)


def clear_all_idp_tokens(user_id: int, db: Session, revoke_at_idp: bool = False) -> None:
    """Clear all locally stored IdP refresh tokens, optionally revoking them remotely."""
    _service().clear_all_idp_tokens(user_id, db, revoke_at_idp)
