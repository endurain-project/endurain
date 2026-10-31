"""Durable-job subscribers for the users module.

The account deletion routes answer 202 and hand the work here, because erasing an account removes rows and
stored files in bulk and does not belong on a request thread. The channel is durable-delivery only: without
``JOBS_ENABLED`` the request runs the same body on an in-process pool.
"""

import jasil.event_versioning as platform_event_versioning
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry

import core.logger as core_logger
import modules.users.users.deletion_job_service as users_deletion_job_service
import modules.users.users.deletion_state_store as users_deletion_state_store
import modules.users.users.events as users_events

logger = core_logger.get_logger(__name__)

DELETION_REQUESTED_SUBSCRIBER_ID = "users.deletion_requested"


def process_deletion_requested_for_event(event: Event) -> None:
    """Durable handler: erase one account; raises on a failure so the worker retries.

    Args:
        event: The ``users.deletion_requested`` event.
    """
    payload = platform_event_versioning.parse_payload(users_events.DeletionRequestedPayload, event)
    platform = platform_runtime.get_active_platform()
    users_deletion_job_service.run_deletion(
        payload,
        users_deletion_state_store.UserDeletionStateStore(platform.state),
        platform.storage,
        will_retry=not event.is_last_attempt,
    )
    logger.debug("Account deletion job finished", extra=core_logger.context(user_id=payload.user_id))


def on_deletion_requested_dead_letter(event: Event, error: str | None) -> None:
    """Close a deletion the runner gave up on.

    Args:
        event: The ``users.deletion_requested`` event.
        error: What the runner recorded, which the deletion's own log line already carries.
    """
    payload = platform_event_versioning.parse_payload(users_events.DeletionRequestedPayload, event)
    users_deletion_job_service.close_dead_lettered_deletion(
        payload, users_deletion_state_store.UserDeletionStateStore(platform_runtime.get_active_platform().state)
    )


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the account deletion handler as a durable job subscriber.

    Args:
        registry: The durable-subscriber registry to register on.
    """
    registry.register(
        users_events.USERS_DELETION_REQUESTED,
        DELETION_REQUESTED_SUBSCRIBER_ID,
        process_deletion_requested_for_event,
        on_dead_letter=on_deletion_requested_dead_letter,
    )
