"""Event subscribers reverse-geocoding activity locations off the ingestion path.

Mirrors the thumbnail subscriber pattern: a durable ``*_for_event`` core that
**raises** so the durable-job runner can retry and eventually dead-letter, and an
``on_*`` bus subscriber that **swallows** so a geocoding failure never breaks
activity import. A lookup the rate limit or an upstream failure held back is
deferred on the durable path and left to the backfill on the bus. The scheduled
backfill (``scheduled_jobs.run_missing_location_backfill``) is the reconciliation
net for any activity the create-path handler misses (delivery dropped on the
best-effort bus, a held-back lookup, etc.).
"""

from datetime import datetime

import jasil.event_versioning as platform_event_versioning
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.jobs import DeferJob
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider
from jasil.subscribers import best_effort

import core.database as core_database
import core.job_queues as core_job_queues
import core.logger as core_logger
import modules.activities.activity.events as activity_events
import modules.activities.activity_geocoding.service as activity_geocoding_service

logger = core_logger.get_logger(__name__)

# Stable durable-subscriber id (independent of module path) so job history and
# dedup survive refactors.
GEOCODING_SUBSCRIBER_ID = "activity_geocoding.reverse_geocode"


def _geocode_created_activity(payload: activity_events.ActivityCreatedPayload) -> datetime | None:
    """Resolve and store a created activity's location.

    Args:
        payload: The ``activity.created`` payload.

    Returns:
        When to look it up again if the lookup was held back, else None.
    """
    with core_database.SessionLocal() as db:
        return activity_geocoding_service.geocode_and_store_activity_location(
            payload.activity_id, platform_runtime.get_active_platform().geocoding, db
        )


def geocode_activity_for_event(event: Event) -> None:
    """Reverse-geocode a created activity's location; raises on failure.

    The durable-job handler for ``activity.created``: any error propagates so the
    runner retries and eventually dead-letters the job. A lookup the rate limit or
    an upstream failure held back ends with ``DeferJob``, so the job runs again
    when the provider says, without spending an attempt. No-ops for activities
    without a GPS stream or whose coordinates do not resolve.

    Args:
        event: The ``activity.created`` event (payload
            ``{"activity_id": "<uuid>", "user_id": "<uuid>", ...}``).

    Raises:
        DeferJob: When the lookup was held back; ``retry_at`` is when to look again.
    """
    payload = platform_event_versioning.parse_payload(activity_events.ActivityCreatedPayload, event)
    retry_at = _geocode_created_activity(payload)
    if retry_at is not None:
        raise DeferJob(retry_at, reason="reverse geocoding lookup held back by the rate limit or the upstream")
    logger.debug(
        "Handled reverse geocoding for created activity",
        extra=core_logger.context(activity_id=str(payload.activity_id), user_id=payload.user_id),
    )


def _geocode_activity_on_bus(event: Event) -> None:
    """Reverse-geocode a created activity, leaving a held-back lookup to the backfill.

    Args:
        event: The ``activity.created`` event.
    """
    payload = platform_event_versioning.parse_payload(activity_events.ActivityCreatedPayload, event)
    if _geocode_created_activity(payload) is not None:
        logger.debug(
            "Left a held-back reverse geocoding lookup to the backfill",
            extra=core_logger.context(activity_id=str(payload.activity_id), user_id=payload.user_id),
        )


# Bus subscriber: reverse-geocodes the activity, swallowing any error so a
# geocoding failure never breaks activity import (the scheduled backfill
# re-resolves any missed activities).
on_activity_created_geocode = best_effort(_geocode_activity_on_bus)


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the geocoding subscriber for ``activity.created``.

    Called once at startup before the event bus is started.

    Args:
        events: The event-bus provider to subscribe on.
    """
    events.subscribe(activity_events.ACTIVITY_CREATED, on_activity_created_geocode)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the geocoding handler as a durable job subscriber.

    Used when durable jobs are enabled: the outbox relay fans ``activity.created``
    out into a retryable job keyed by this subscriber id, and the worker resolves
    it back to the raising ``*_for_event`` core.

    Args:
        registry: The durable-subscriber registry to register on.
    """
    registry.register(
        activity_events.ACTIVITY_CREATED,
        GEOCODING_SUBSCRIBER_ID,
        geocode_activity_for_event,
        queue=core_job_queues.BACKGROUND,
    )
