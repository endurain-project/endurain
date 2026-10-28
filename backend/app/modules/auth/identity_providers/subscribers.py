"""Event subscribers that refresh identity-provider tokens outside the request that asked."""

import jasil.event_versioning as platform_event_versioning
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider
from jasil.subscribers import best_effort

import core.config as core_config
import core.logger as core_logger
import modules.auth.identity_providers.events as idp_events
import modules.auth.identity_providers.service as idp_service

logger = core_logger.get_logger(__name__)
IDP_TOKEN_REFRESH_SUBSCRIBER_ID = "auth.refresh_idp_tokens"  # noqa: S105 - subscriber id, not a credential


def refresh_idp_tokens_for_event(event: Event) -> None:
    """Refresh the user's expiring identity-provider tokens for a refresh request."""
    payload = platform_event_versioning.parse_payload(idp_events.IdpTokenRefreshPayload, event)
    service = idp_service.IdentityProviderService(
        platform_runtime.get_state(), core_config.settings.ENDURAIN_HOST, core_config.API_VERSION
    )
    service.refresh_idp_tokens(payload.user_id)
    logger.debug("IdP token refresh event processed", extra=core_logger.context(user_id=payload.user_id))


on_idp_token_refresh_requested = best_effort(refresh_idp_tokens_for_event)


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the identity-provider bus subscribers."""
    events.subscribe(idp_events.IDP_TOKEN_REFRESH_REQUESTED, on_idp_token_refresh_requested)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the retryable identity-provider durable handlers."""
    registry.register(
        idp_events.IDP_TOKEN_REFRESH_REQUESTED,
        IDP_TOKEN_REFRESH_SUBSCRIBER_ID,
        refresh_idp_tokens_for_event,
    )
