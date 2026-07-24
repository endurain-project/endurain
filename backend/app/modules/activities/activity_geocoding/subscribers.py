"""Event subscribers reverse-geocoding activity locations off the ingestion path.

Mirrors the thumbnail / HR-zone subscriber pattern: a durable
``*_for_event`` core that **raises** so the durable-job runner can retry and
eventually dead-letter, and an ``on_*`` bus subscriber that **swallows** so a
geocoding failure never breaks activity import. The scheduled backfill
(:func:`run_missing_location_backfill`) is the reconciliation net for any activity
the create-path handler misses (delivery dropped on the best-effort bus, provider
temporarily down, etc.).
"""

import core.database as core_database
import core.logger as core_logger
import infra.runtime as platform_runtime
import modules.activities.activity.events as activity_events
import modules.activities.activity_geocoding.service as activity_geocoding_service
from infra.events import Event
from infra.jobs.registry import JobHandlerRegistry
from infra.providers import EventBusProvider

# Stable durable-subscriber id (independent of module path) so job history and
# dedup survive refactors.
GEOCODING_SUBSCRIBER_ID = "activity_geocoding.reverse_geocode"


def geocode_activity_for_event(event: Event) -> None:
    """Reverse-geocode a created activity's location; raises on failure.

    The durable-job handler for ``activity.created``: any error propagates so the
    runner retries and eventually dead-letters the job. No-ops for activities
    without a GPS stream or whose coordinates do not resolve.

    Args:
        event: The ``activity.created`` event (payload
            ``{"activity_id": int, "user_id": int, ...}``).

    Returns:
        None.
    """
    payload = activity_events.ActivityCreatedPayload.model_validate(event.payload)
    with core_database.SessionLocal() as db:
        activity_geocoding_service.geocode_and_store_activity_location(payload.activity_id, payload.user_id, db)


def on_activity_created_geocode(event: Event) -> None:
    """Bus subscriber: reverse-geocode the activity, swallowing any error.

    Wraps :func:`geocode_activity_for_event` so a geocoding failure never breaks
    activity import (the scheduled backfill re-resolves any missed activities).

    Args:
        event: The ``activity.created`` event.

    Returns:
        None.
    """
    try:
        geocode_activity_for_event(event)
    except Exception as err:
        core_logger.print_to_log(
            f"activity.created geocoding handler failed for activity {event.payload.get('activity_id')}: {err}",
            "error",
            exc=err,
        )


def register_geocoding_subscribers(events: EventBusProvider) -> None:
    """Register the geocoding subscriber for ``activity.created``.

    Called once at startup before the event bus is started.

    Args:
        events: The event-bus provider to subscribe on.

    Returns:
        None.
    """
    events.subscribe(activity_events.ACTIVITY_CREATED, on_activity_created_geocode)


def register_geocoding_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the geocoding handler as a durable job subscriber.

    Used when durable jobs are enabled: the outbox relay fans ``activity.created``
    out into a retryable job keyed by this subscriber id, and the worker resolves
    it back to the raising ``*_for_event`` core.

    Args:
        registry: The durable-subscriber registry to register on.

    Returns:
        None.
    """
    registry.register(
        activity_events.ACTIVITY_CREATED,
        GEOCODING_SUBSCRIBER_ID,
        geocode_activity_for_event,
    )


def run_missing_location_backfill() -> None:
    """Scheduled reconciliation net: geocode GPS activities missing a location.

    Intended to be called periodically by the scheduler. Acquires the coordination
    lock so only one replica runs the pass, then opens its own database session and
    resolves any GPS activities the create-path handler missed.

    Returns:
        None.

    Raises:
        None — the service backfill logs and continues per activity.
    """
    platform = platform_runtime.get_active_platform()
    with platform.lock.try_acquire("location_backfill") as acquired:
        if not acquired:
            core_logger.print_to_log(
                "Geocoding scheduler: another replica holds the backfill lock; skipping",
                "debug",
            )
            return
        with core_database.SessionLocal() as db:
            activity_geocoding_service.backfill_missing_activity_locations(db)
