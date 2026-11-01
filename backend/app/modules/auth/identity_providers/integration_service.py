"""Identity-provider operations exposed to auth peers."""

from collections.abc import Callable

import jasil.runtime as platform_runtime
from jasil.providers import StateProvider
from sqlalchemy.orm import Session

import core.config as core_config
import modules.auth.identity_provider_links.contracts as identity_links_contracts
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_provider_links.schema as identity_links_schema
import modules.auth.identity_providers.authorization_service as identity_providers_authorization
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.identity_providers.contracts as identity_providers_contracts
import modules.auth.identity_providers.crud as identity_providers_crud
import modules.auth.identity_providers.oidc_client_service as identity_providers_oidc_client
import modules.auth.identity_providers.step_up_ticket_store as identity_providers_step_up_tickets
import modules.auth.identity_providers.token_service as identity_providers_tokens


def _oidc_client() -> identity_providers_oidc_client.OidcClientService:
    """Resolve runtime state and build the provider client at this entrypoint."""
    return identity_providers_oidc_client.OidcClientService(platform_runtime.get_state(), core_config.API_VERSION)


def _authorization_service() -> identity_providers_authorization.AuthorizationService:
    """Build the service that starts provider flows at this entrypoint."""
    return identity_providers_authorization.AuthorizationService(_oidc_client(), core_config.settings.ENDURAIN_HOST)


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


def stage_browser_link(
    link_token: str,
    idp_id: int,
    redirect: str | None,
    client_ip: str | None,
    claim_link_token: Callable[..., int],
    db: Session,
) -> identity_providers_contracts.StagedBrowserFlow:
    """Claim a browser link token and stage the link's OAuth state; the caller commits, then builds the URL."""
    return _authorization_service().stage_browser_link(
        link_token,
        idp_id,
        redirect,
        client_ip,
        claim_link_token,
        core_config.settings.ALLOWED_REDIRECT_SCHEMES,
        db,
    )


def stage_step_up(
    user_id: int,
    session_id: str,
    idp_id: int,
    action: identity_providers_constants.StepUpAction,
    code_challenge: str,
    redirect: str,
    client_ip: str | None,
    db: Session,
) -> identity_providers_contracts.StagedBrowserFlow:
    """Stage a step-up re-authentication's OAuth state; the caller commits, then builds the URL."""
    return _authorization_service().stage_step_up(
        user_id, session_id, idp_id, action, code_challenge, redirect, client_ip, db
    )


def authorization_url(staged: identity_providers_contracts.StagedBrowserFlow) -> str:
    """Build the provider URL of a committed link or step-up; it touches no database."""
    return _authorization_service().authorization_url(staged)


def read_step_up_ticket(state: StateProvider, ticket: str) -> identity_providers_contracts.StepUpTicket | None:
    """Return a step-up ticket without redeeming it."""
    return identity_providers_step_up_tickets.StepUpTicketStore(state).read(ticket)


def redeem_step_up_ticket(state: StateProvider, ticket: str) -> identity_providers_contracts.StepUpTicket | None:
    """Redeem a step-up ticket atomically, so it pays for exactly one request."""
    return identity_providers_step_up_tickets.StepUpTicketStore(state).redeem(ticket)


def request_idp_token_refresh(user_id: int, db: Session) -> None:
    """Clear the user's retired IdP tokens now and queue the refresh of those expiring, with the caller's commit."""
    identity_providers_tokens.IdpTokenService(_oidc_client()).request_idp_token_refresh(user_id, db)


def clear_all_idp_tokens(user_id: int, db: Session, revoke_at_idp: bool = False) -> None:
    """Clear all locally stored IdP refresh tokens, optionally revoking them remotely."""
    identity_providers_tokens.IdpTokenService(_oidc_client()).clear_all_idp_tokens(user_id, db, revoke_at_idp)
