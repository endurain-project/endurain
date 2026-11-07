"""Event subscribers that refresh and revoke identity-provider tokens outside the request that asked."""

import jasil.event_versioning as platform_event_versioning
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider
from jasil.subscribers import best_effort

import core.config as core_config
import core.logger as core_logger
import modules.auth.identity_providers.events as idp_events
import modules.auth.identity_providers.oidc_client_service as idp_oidc_client
import modules.auth.identity_providers.refresh_claim_store as idp_refresh_claim_store
import modules.auth.identity_providers.token_revocation_service as idp_token_revocation_service
import modules.auth.identity_providers.token_service as idp_token_service
import modules.auth.sessions.events as sessions_events

logger = core_logger.get_logger(__name__)
IDP_TOKEN_REFRESH_SUBSCRIBER_ID = "auth.refresh_idp_tokens"  # noqa: S105 - subscriber id, not a credential
IDP_TOKEN_REVOKE_SUBSCRIBER_ID = "auth.revoke_idp_session_tokens"  # noqa: S105 - subscriber id, not a credential


def refresh_idp_tokens_for_event(event: Event) -> None:
    """Refresh the session's expiring identity-provider token for a refresh request."""
    payload = platform_event_versioning.parse_payload(idp_events.IdpTokenRefreshPayload, event)
    if payload.session_id is None:
        logger.debug(
            "Dropped an IdP token refresh event that names no session",
            extra=core_logger.context(user_id=payload.user_id),
        )
        return
    oidc = idp_oidc_client.OidcClientService(platform_runtime.get_state(), core_config.API_VERSION)
    service = idp_token_service.IdpTokenService(oidc)
    service.refresh_idp_tokens(
        payload.user_id, payload.session_id, idp_refresh_claim_store.IdpRefreshClaimStore(platform_runtime.get_state())
    )
    logger.debug("IdP token refresh event processed", extra=core_logger.context(user_id=payload.user_id))


def revoke_session_tokens_for_event(event: Event) -> None:
    """Revoke at their providers the tokens of the user's sessions that ended."""
    payload = platform_event_versioning.parse_payload(sessions_events.SessionsRevokedPayload, event)
    oidc = idp_oidc_client.OidcClientService(platform_runtime.get_state(), core_config.API_VERSION)
    revoked = idp_token_revocation_service.IdpTokenRevocationService(oidc).revoke_ended_sessions(
        user_id=payload.user_id
    )
    logger.debug(
        "IdP token revocation event processed", extra=core_logger.context(user_id=payload.user_id, revoked=revoked)
    )


on_idp_token_refresh_requested = best_effort(refresh_idp_tokens_for_event)
on_sessions_revoked_revoke_idp_tokens = best_effort(revoke_session_tokens_for_event)


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the identity-provider bus subscribers."""
    events.subscribe(idp_events.IDP_TOKEN_REFRESH_REQUESTED, on_idp_token_refresh_requested)
    events.subscribe(sessions_events.SESSIONS_REVOKED, on_sessions_revoked_revoke_idp_tokens)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the retryable identity-provider durable handlers."""
    registry.register(
        idp_events.IDP_TOKEN_REFRESH_REQUESTED,
        IDP_TOKEN_REFRESH_SUBSCRIBER_ID,
        refresh_idp_tokens_for_event,
    )
    registry.register(
        sessions_events.SESSIONS_REVOKED,
        IDP_TOKEN_REVOKE_SUBSCRIBER_ID,
        revoke_session_tokens_for_event,
    )
