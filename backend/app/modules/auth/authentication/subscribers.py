"""Event subscribers owned by the authentication package."""

import jasil.event_versioning as platform_event_versioning
from jasil.events import Event
from jasil.providers import EventBusProvider
from jasil.subscribers import best_effort

import core.database as core_database
import core.logger as core_logger
import modules.auth.api_keys.integration_service as api_keys_integration
import modules.auth.authentication.events as authentication_events

logger = core_logger.get_logger(__name__)


def record_api_key_use_for_event(event: Event) -> None:
    """Record the time an API key last authenticated a request."""
    payload = platform_event_versioning.parse_payload(authentication_events.ApiKeyUsedPayload, event)
    with core_database.SessionLocal() as db:
        api_keys_integration.update_last_used(payload.api_key_id, db)
        db.commit()
    logger.debug("API key last-used time recorded")


on_api_key_used = best_effort(record_api_key_use_for_event)


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the authentication event consumers on the running bus."""
    events.subscribe(authentication_events.API_KEY_USED, on_api_key_used)
