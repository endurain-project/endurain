"""Event subscribers computing HR zone percentages off the ingestion path.

Mirrors the thumbnail/notification subscriber pattern: a durable
``*_for_event`` core that **raises** so the durable-job runner can retry and
eventually dead-letter, and an ``on_*`` bus subscriber that **swallows** so an
HR-zone failure never breaks activity import. The scheduled backfill
(:func:`run_missing_hr_zone_backfill`) is the reconciliation net for any streams the
create-path handler misses (e.g. delivery dropped on the best-effort bus, or the
owner's max heart rate was set only later).
"""

import core.database as core_database
import core.logger as core_logger
import infra.runtime as platform_runtime
import modules.activities.activity.events as activity_events
import modules.activities.activity_streams.crud as activity_streams_crud
from infra.events import Event
from infra.jobs.registry import JobHandlerRegistry
from infra.providers import EventBusProvider
from infra.subscribers import best_effort

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
    payload = activity_events.ActivityCreatedPayload.model_validate(event.payload)
    with core_database.SessionLocal() as db:
        activity_streams_crud.compute_and_store_hr_zone_percentages_for_activity(
            payload.activity_id, payload.user_id, db
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
            core_logger.print_to_log(
                "HR-zone scheduler: another replica holds the backfill lock; skipping",
                "debug",
            )
            return
        with core_database.SessionLocal() as db:
            updated = activity_streams_crud.backfill_missing_hr_zone_percentages(db)
        core_logger.print_to_log(
            f"HR-zone scheduler: backfilled zone percentages for {updated} stream(s)",
            "info" if updated else "debug",
        )
