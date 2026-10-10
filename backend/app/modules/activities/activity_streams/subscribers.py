"""Event subscribers computing HR zone percentages off the ingestion path.

Mirrors the thumbnail/notification subscriber pattern: a durable
``*_for_event`` core that **raises** so the durable-job runner can retry and
eventually dead-letter, and an ``on_*`` bus subscriber that **swallows** so an
HR-zone failure never breaks activity import. The scheduled backfill
(:func:`run_missing_hr_zone_backfill`) is the reconciliation net for any streams the
create-path handler misses (e.g. delivery dropped on the best-effort bus, or the
owner's max heart rate was set only later).
"""

import logging

import jasil.event_versioning as platform_event_versioning
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider
from jasil.subscribers import best_effort

import core.database as core_database
import core.logger as core_logger
import modules.activities.activity.events as activity_events
import modules.activities.activity_streams.service as activity_streams_service

logger = core_logger.get_logger(__name__)

# Stable durable-subscriber id (independent of module path) so job history and
# dedup survive refactors.
HR_ZONE_SUBSCRIBER_ID = "activity_streams.compute_hr_zones"


def compute_hr_zones_for_event(event: Event) -> None:
    """Compute HR zone percentages for a created activity; raises on failure.

    The durable-job handler for ``activity.created``: any error propagates so the
    runner retries and eventually dead-letters the job. No-ops for activities
    without an HR stream or whose owner has no resolvable max heart rate.

    Args:
        event: The ``activity.created`` event (payload
            ``{"activity_id": int, "user_id": int, ...}``).

    Returns:
        None.
    """
    payload = platform_event_versioning.parse_payload(activity_events.ActivityCreatedPayload, event)
    with core_database.SessionLocal() as db:
        activity_streams_service.score_activity_hr_zones(payload.activity_id, payload.user_id, db)
    logger.debug(
        "Handled HR zone computation for created activity",
        extra=core_logger.context(activity_id=payload.activity_id, user_id=payload.user_id),
    )


# Bus subscriber: computes HR zones, swallowing any error so an HR-zone failure
# never breaks activity import (the scheduled backfill scores any missed streams).
on_activity_created_compute_hr_zones = best_effort(compute_hr_zones_for_event)


def register_hr_zone_subscribers(events: EventBusProvider) -> None:
    """Register the HR-zone subscriber for ``activity.created``.

    Called once at startup before the event bus is started.

    Args:
        events: The event-bus provider to subscribe on.

    Returns:
        None.
    """
    events.subscribe(activity_events.ACTIVITY_CREATED, on_activity_created_compute_hr_zones)


def register_hr_zone_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the HR-zone handler as a durable job subscriber.

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
        HR_ZONE_SUBSCRIBER_ID,
        compute_hr_zones_for_event,
    )


def run_missing_hr_zone_backfill() -> None:
    """Scheduled reconciliation net: score HR streams missing ``zone_percentages``.

    Intended to be called periodically by the scheduler. Acquires the coordination
    lock so only one replica runs the pass, then opens its own database session and
    scores any HR streams the create-path handler missed.

    Returns:
        None.

    Raises:
        None — the crud backfill logs and continues per batch.
    """
    platform = platform_runtime.get_active_platform()
    with platform.lock.try_acquire("hr_zone_backfill") as acquired:
        if not acquired:
            logger.debug("HR-zone scheduler: another replica holds the backfill lock; skipping")
            return
        with core_database.SessionLocal() as db:
            updated = activity_streams_service.backfill_missing_hr_zones(db)
        # Level varies so an idle scheduler pass stays at debug instead of
        # emitting an INFO line every tick.
        logger.log(
            logging.INFO if updated else logging.DEBUG,
            "HR-zone scheduler pass complete",
            extra=core_logger.context(updated=updated),
        )
