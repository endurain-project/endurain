"""Durable-job subscribers for the gear package.

The gear delete route answers 202 and hands the work here, because unassigning a gear from every activity that
carries it writes rows in bulk and does not belong on a request thread. The channel is durable-delivery only:
without ``JOBS_ENABLED`` the request runs the same body on an in-process pool.
"""

import jasil.event_versioning as platform_event_versioning
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry

import core.job_queues as core_job_queues
import core.logger as core_logger
import modules.gears.gear.deletion_job_service as gears_deletion_job_service
import modules.gears.gear.deletion_state_store as gears_deletion_state_store
import modules.gears.gear.events as gears_events

logger = core_logger.get_logger(__name__)

DELETION_REQUESTED_SUBSCRIBER_ID = "gears.deletion_requested"


def process_deletion_requested_for_event(event: Event) -> None:
    """Durable handler: delete one gear; raises on a failure so the worker retries.

    Args:
        event: The ``gears.deletion_requested`` event.
    """
    payload = platform_event_versioning.parse_payload(gears_events.DeletionRequestedPayload, event)
    gears_deletion_job_service.run_gear_deletion(
        payload,
        gears_deletion_state_store.GearDeletionStateStore(platform_runtime.get_active_platform().state),
        will_retry=not event.is_last_attempt,
    )
    logger.debug("Gear deletion job finished", extra=core_logger.context(gear_id=payload.gear_id))


def on_deletion_requested_dead_letter(event: Event, error: str | None) -> None:
    """Close a deletion the runner gave up on.

    Args:
        event: The ``gears.deletion_requested`` event.
        error: What the runner recorded, which the deletion's own log line already carries.
    """
    payload = platform_event_versioning.parse_payload(gears_events.DeletionRequestedPayload, event)
    gears_deletion_job_service.close_dead_lettered_deletion(
        payload, gears_deletion_state_store.GearDeletionStateStore(platform_runtime.get_active_platform().state)
    )


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the gear deletion handler as a durable job subscriber.

    Args:
        registry: The durable-subscriber registry to register on.
    """
    registry.register(
        gears_events.GEAR_DELETION_REQUESTED,
        DELETION_REQUESTED_SUBSCRIBER_ID,
        process_deletion_requested_for_event,
        on_dead_letter=on_deletion_requested_dead_letter,
        queue=core_job_queues.BACKGROUND,
    )
