"""Durable-job subscribers for the activity package.

The bulk visibility edit route answers 202 and hands the work here, because changing every activity a user
owns writes rows in bulk and does not belong on a request thread. The channel is durable-delivery only:
without ``JOBS_ENABLED`` the request runs the same body on an in-process pool.
"""

import jasil.event_versioning as platform_event_versioning
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry

import core.logger as core_logger
import modules.activities.activity.bulk_edit_job_service as bulk_edit_job_service
import modules.activities.activity.bulk_edit_state_store as bulk_edit_state_store
import modules.activities.activity.events as activity_events

logger = core_logger.get_logger(__name__)

VISIBILITY_EDIT_REQUESTED_SUBSCRIBER_ID = "activities.visibility_edit_requested"


def process_visibility_edit_requested_for_event(event: Event) -> None:
    """Durable handler: apply one bulk visibility edit; raises on a failure so the worker retries.

    Args:
        event: The ``activities.visibility_edit_requested`` event.
    """
    payload = platform_event_versioning.parse_payload(activity_events.VisibilityEditRequestedPayload, event)
    bulk_edit_job_service.run_visibility_edit(
        payload,
        bulk_edit_state_store.ActivityBulkEditStateStore(platform_runtime.get_active_platform().state),
        will_retry=not event.is_last_attempt,
    )
    logger.debug("Bulk visibility edit job finished", extra=core_logger.context(user_id=payload.user_id))


def on_visibility_edit_requested_dead_letter(event: Event, error: str | None) -> None:
    """Close an edit the runner gave up on.

    Args:
        event: The ``activities.visibility_edit_requested`` event.
        error: What the runner recorded, which the edit's own log line already carries.
    """
    payload = platform_event_versioning.parse_payload(activity_events.VisibilityEditRequestedPayload, event)
    bulk_edit_job_service.close_dead_lettered_visibility_edit(
        payload, bulk_edit_state_store.ActivityBulkEditStateStore(platform_runtime.get_active_platform().state)
    )


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the bulk visibility edit handler as a durable job subscriber.

    Args:
        registry: The durable-subscriber registry to register on.
    """
    registry.register(
        activity_events.ACTIVITIES_VISIBILITY_EDIT_REQUESTED,
        VISIBILITY_EDIT_REQUESTED_SUBSCRIBER_ID,
        process_visibility_edit_requested_for_event,
        on_dead_letter=on_visibility_edit_requested_dead_letter,
    )
