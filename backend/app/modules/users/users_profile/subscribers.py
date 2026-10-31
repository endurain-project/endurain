"""Subscribers that run a queued profile import or export.

The import route answers 202 and publishes ``users.profile_import_requested``. With durable jobs a
worker runs the durable handler and retries a transient failure; without them the bus subscriber
runs the same body on the in-process subscriber pool, where nothing retries it.
"""

import jasil.event_versioning as platform_event_versioning
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider
from jasil.subscribers import best_effort

import core.local_pool as core_local_pool
import core.logger as core_logger
import modules.users.users_profile.events as profile_events
import modules.users.users_profile.export_job_service as profile_export_job_service
import modules.users.users_profile.export_state_store as profile_export_state_store
import modules.users.users_profile.import_job_service as profile_import_job_service
import modules.users.users_profile.import_state_store as profile_import_state_store
import modules.users.users_profile.transfer_pool as profile_transfer_pool

logger = core_logger.get_logger(__name__)

IMPORT_REQUESTED_SUBSCRIBER_ID = "users.profile_import_requested"
EXPORT_REQUESTED_SUBSCRIBER_ID = "users.profile_export_requested"


def _import(event: Event, *, will_retry: bool) -> int:
    """Run the import the event names.

    Args:
        event: The ``users.profile_import_requested`` event.
        will_retry: Whether a worker runs this again if it raises.

    Returns:
        The importing user's ID.
    """
    payload = platform_event_versioning.parse_payload(profile_events.ProfileImportRequestedPayload, event)
    platform = platform_runtime.get_active_platform()
    profile_import_job_service.run_import(
        payload,
        profile_import_state_store.ProfileImportStateStore(platform.state),
        platform.storage,
        will_retry=will_retry,
    )
    return payload.user_id


def process_import_requested_for_event(event: Event) -> None:
    """Durable handler: import one staged archive; raises on a transient failure so the worker retries.

    Args:
        event: The ``users.profile_import_requested`` event.
    """
    user_id = _import(event, will_retry=not event.is_last_attempt)
    logger.debug("Profile import job finished", extra=core_logger.context(user_id=user_id))


def run_import_requested_on_bus(event: Event) -> None:
    """Bus subscriber: hand the import to the transfer pool; nothing retries it.

    The import runs on the profile transfer pool so it does not hold a subscriber thread for minutes.
    An import the full pool refuses is closed as failed, since nothing else would finish its claim.

    Args:
        event: The ``users.profile_import_requested`` event.
    """
    try:
        profile_transfer_pool.pool.submit(_import, event, will_retry=False)
    except core_local_pool.PoolFullError:
        payload = platform_event_versioning.parse_payload(profile_events.ProfileImportRequestedPayload, event)
        platform = platform_runtime.get_active_platform()
        profile_import_job_service.fail_unstarted_import(
            payload, profile_import_state_store.ProfileImportStateStore(platform.state), platform.storage
        )


on_import_requested = best_effort(run_import_requested_on_bus)


def _export(event: Event, *, will_retry: bool) -> int:
    """Run the export the event names.

    Args:
        event: The ``users.profile_export_requested`` event.
        will_retry: Whether a worker runs this again if it raises.

    Returns:
        The exporting user's ID.
    """
    payload = platform_event_versioning.parse_payload(profile_events.ProfileExportRequestedPayload, event)
    platform = platform_runtime.get_active_platform()
    profile_export_job_service.run_export(
        payload,
        profile_export_state_store.ProfileExportStateStore(platform.state),
        platform.storage,
        will_retry=will_retry,
    )
    return payload.user_id


def process_export_requested_for_event(event: Event) -> None:
    """Durable handler: build one export; raises on a transient failure so the worker retries.

    Args:
        event: The ``users.profile_export_requested`` event.
    """
    user_id = _export(event, will_retry=not event.is_last_attempt)
    logger.debug("Profile export job finished", extra=core_logger.context(user_id=user_id))


def run_export_requested_on_bus(event: Event) -> None:
    """Bus subscriber: hand the export to the transfer pool; nothing retries it.

    An export the full pool refuses is closed as failed, since nothing else would finish its claim.

    Args:
        event: The ``users.profile_export_requested`` event.
    """
    try:
        profile_transfer_pool.pool.submit(_export, event, will_retry=False)
    except core_local_pool.PoolFullError:
        payload = platform_event_versioning.parse_payload(profile_events.ProfileExportRequestedPayload, event)
        platform = platform_runtime.get_active_platform()
        profile_export_job_service.fail_unstarted_export(
            payload, profile_export_state_store.ProfileExportStateStore(platform.state)
        )


on_export_requested = best_effort(run_export_requested_on_bus)


def on_import_requested_dead_letter(event: Event, error: str | None) -> None:
    """Close an import the runner gave up on.

    Args:
        event: The ``users.profile_import_requested`` event.
        error: What the runner recorded, which the import's own log line already carries.
    """
    payload = platform_event_versioning.parse_payload(profile_events.ProfileImportRequestedPayload, event)
    platform = platform_runtime.get_active_platform()
    profile_import_job_service.close_dead_lettered_import(
        payload, profile_import_state_store.ProfileImportStateStore(platform.state), platform.storage
    )


def on_export_requested_dead_letter(event: Event, error: str | None) -> None:
    """Close an export the runner gave up on.

    Args:
        event: The ``users.profile_export_requested`` event.
        error: What the runner recorded, which the export's own log line already carries.
    """
    payload = platform_event_versioning.parse_payload(profile_events.ProfileExportRequestedPayload, event)
    platform = platform_runtime.get_active_platform()
    profile_export_job_service.close_dead_lettered_export(
        payload, profile_export_state_store.ProfileExportStateStore(platform.state)
    )


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the import and export consumers on the running bus.

    Args:
        events: The event bus.
    """
    events.subscribe(profile_events.USERS_PROFILE_IMPORT_REQUESTED, on_import_requested)
    events.subscribe(profile_events.USERS_PROFILE_EXPORT_REQUESTED, on_export_requested)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the import and export handlers as durable job subscribers.

    Args:
        registry: The durable-subscriber registry to register on.
    """
    registry.register(
        profile_events.USERS_PROFILE_IMPORT_REQUESTED,
        IMPORT_REQUESTED_SUBSCRIBER_ID,
        process_import_requested_for_event,
        on_dead_letter=on_import_requested_dead_letter,
    )
    registry.register(
        profile_events.USERS_PROFILE_EXPORT_REQUESTED,
        EXPORT_REQUESTED_SUBSCRIBER_ID,
        process_export_requested_for_event,
        on_dead_letter=on_export_requested_dead_letter,
    )
