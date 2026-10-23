"""Application composition for installed module runtime contributions."""

import contextvars
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import jasil.settings as jasil_settings
from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider, RealtimeProvider

import core.config as core_config
import core.database as core_database
import core.geocoding as core_geocoding
import core.logger as core_logger
import core.mail as core_mail
import core.scheduler as core_scheduler
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity_exercise_titles.integration_service as activity_exercise_titles_integration
import modules.activities.activity_file_storage.scheduled_jobs as activity_file_storage_scheduled_jobs
import modules.activities.activity_file_storage.subscriber_registry as activity_file_storage_subscriber_registry
import modules.activities.activity_geocoding.scheduled_jobs as activity_geocoding_scheduled_jobs
import modules.activities.activity_geocoding.subscriber_registry as activity_geocoding_subscriber_registry
import modules.activities.activity_ingestion.scheduled_jobs as activity_ingestion_scheduled_jobs
import modules.activities.activity_ingestion.subscriber_registry as activity_ingestion_subscriber_registry
import modules.activities.activity_laps.integration_service as activity_laps_integration
import modules.activities.activity_media.integration_service as activity_media_integration
import modules.activities.activity_media.scheduled_jobs as activity_media_scheduled_jobs
import modules.activities.activity_media.subscriber_registry as activity_media_subscriber_registry
import modules.activities.activity_sets.integration_service as activity_sets_integration
import modules.activities.activity_streams.integration_service as activity_streams_integration
import modules.activities.activity_thumbnail.integration_service as activity_thumbnail_integration
import modules.activities.activity_thumbnail.scheduled_jobs as activity_thumbnail_scheduled_jobs
import modules.activities.activity_thumbnail.subscriber_registry as activity_thumbnail_subscriber_registry
import modules.activities.activity_workout_steps.integration_service as activity_workout_steps_integration
import modules.activities.contributor_registry as activities_contributor_registry
import modules.auth.password_reset_tokens.subscriber_registry as password_reset_tokens_subscriber_registry
import modules.auth.sign_up_tokens.subscriber_registry as sign_up_tokens_subscriber_registry
import modules.gears.contributor_registry as gears_contributor_registry
import modules.gears.contributors as gears_contributors
import modules.gears.gear_components.integration_service as gear_components_integration
import modules.notifications.scheduled_jobs as notifications_scheduled_jobs
import modules.notifications.subscriber_registry as notifications_subscriber_registry
import modules.server_settings.integration_service as server_settings_integration
import modules.websocket.subscriber_registry as websocket_subscriber_registry

logger = core_logger.get_logger(__name__)

#: How long the mail and geocoding settings are reused before the database is read again.
_SETTINGS_CACHE_SECONDS = 5.0

# Small on purpose: derived work (thumbnails, cleanup, notifications) must not
# compete with request threads for the process.
_DEFERRED_SUBSCRIBER_WORKERS = 2

_deferred_executor: ThreadPoolExecutor | None = None


def _get_deferred_executor() -> ThreadPoolExecutor:
    """Return the pool in-process bus subscribers run on, creating it on first use.

    Returns:
        The shared subscriber thread pool.
    """
    global _deferred_executor
    if _deferred_executor is None:
        _deferred_executor = ThreadPoolExecutor(
            max_workers=_DEFERRED_SUBSCRIBER_WORKERS, thread_name_prefix="event-subscriber"
        )
    return _deferred_executor


def shutdown_deferred_subscribers() -> None:
    """Stop the subscriber pool without waiting; queued work is repaired by the reconciliation nets."""
    global _deferred_executor
    if _deferred_executor is not None:
        _deferred_executor.shutdown(wait=False, cancel_futures=True)
        _deferred_executor = None


def _log_deferred_failure(handler_name: str, future) -> None:
    """Log an exception escaping a deferred subscriber.

    Args:
        handler_name: The subscriber's name.
        future: The completed future.
    """
    error = future.exception()
    if error is not None:
        logger.error(
            "Deferred event subscriber failed", exc_info=error, extra=core_logger.context(handler=handler_name)
        )


class _DeferredSubscriptions:
    """Event-bus facade that runs each subscriber on a background pool.

    The in-process bus calls subscribers inline, so a request that publishes
    would wait for every subscriber (map tiles, storage deletes, notifications).
    Handlers registered through this facade are queued instead, and run with the
    publisher's context so the request id still correlates their logs. Only
    ``subscribe`` is exposed: that is all a module's registration needs.
    """

    def __init__(self, events: EventBusProvider) -> None:
        self._events = events

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Subscribe a handler that runs off the publishing thread.

        Args:
            event_type: The event channel.
            handler: The subscriber to run.
        """

        def deferred(event) -> None:
            context = contextvars.copy_context()
            future = _get_deferred_executor().submit(context.run, handler, event)
            future.add_done_callback(lambda done: _log_deferred_failure(handler.__name__, done))

        deferred.__name__ = handler.__name__
        self._events.subscribe(event_type, deferred)


RegisterBus = Callable[[EventBusProvider], None]
RegisterRealtime = Callable[[RealtimeProvider], None]
RegisterDurable = Callable[[JobHandlerRegistry], None]
RecurringJobs = Callable[[], tuple[core_scheduler.ScheduledJob, ...]]


@dataclass(frozen=True)
class StartupTask:
    """One best-effort startup task contributed by a module."""

    name: str
    description: str
    func: Callable[[], None]


@dataclass(frozen=True, kw_only=True)
class RuntimeModule:
    """Runtime wiring published by one installed module."""

    name: str
    register_bus: RegisterBus | None = None
    register_realtime: RegisterRealtime | None = None
    register_durable: RegisterDurable | None = None
    nets: tuple[DurableSubscriberNet, ...] = ()
    recurring_jobs: RecurringJobs | None = None
    startup_tasks: tuple[StartupTask, ...] = ()


MODULES: tuple[RuntimeModule, ...] = (
    RuntimeModule(
        name="activity_thumbnail",
        register_bus=activity_thumbnail_subscriber_registry.register_bus_subscribers,
        register_durable=activity_thumbnail_subscriber_registry.register_durable_handlers,
        nets=activity_thumbnail_subscriber_registry.DURABLE_SUBSCRIBER_NETS,
        recurring_jobs=activity_thumbnail_scheduled_jobs.recurring_jobs,
        startup_tasks=(
            StartupTask(
                "generate_missing_thumbnails",
                "Scheduling missing activity map thumbnail generation",
                activity_thumbnail_scheduled_jobs.schedule_missing_thumbnail_generation,
            ),
        ),
    ),
    RuntimeModule(
        name="activity_geocoding",
        register_bus=activity_geocoding_subscriber_registry.register_bus_subscribers,
        register_durable=activity_geocoding_subscriber_registry.register_durable_handlers,
        nets=activity_geocoding_subscriber_registry.DURABLE_SUBSCRIBER_NETS,
        recurring_jobs=activity_geocoding_scheduled_jobs.recurring_jobs,
        startup_tasks=(
            StartupTask(
                "backfill_missing_locations",
                "Scheduling missing activity location backfill",
                activity_geocoding_scheduled_jobs.schedule_missing_location_backfill,
            ),
        ),
    ),
    RuntimeModule(
        name="activity_file_storage",
        register_bus=activity_file_storage_subscriber_registry.register_bus_subscribers,
        register_durable=activity_file_storage_subscriber_registry.register_durable_handlers,
        nets=activity_file_storage_subscriber_registry.DURABLE_SUBSCRIBER_NETS,
        recurring_jobs=activity_file_storage_scheduled_jobs.recurring_jobs,
    ),
    RuntimeModule(
        name="activity_media",
        register_bus=activity_media_subscriber_registry.register_bus_subscribers,
        register_durable=activity_media_subscriber_registry.register_durable_handlers,
        nets=activity_media_subscriber_registry.DURABLE_SUBSCRIBER_NETS,
        recurring_jobs=activity_media_scheduled_jobs.recurring_jobs,
    ),
    RuntimeModule(
        name="activity_ingestion",
        register_durable=activity_ingestion_subscriber_registry.register_durable_handlers,
        nets=activity_ingestion_subscriber_registry.DURABLE_SUBSCRIBER_NETS,
        recurring_jobs=activity_ingestion_scheduled_jobs.recurring_jobs,
        startup_tasks=(
            StartupTask(
                "queue_provider_refreshes",
                "Queueing a provider activity refresh for every linked user",
                activity_ingestion_scheduled_jobs.schedule_provider_refresh,
            ),
        ),
    ),
    RuntimeModule(
        name="password_reset_tokens",
        register_bus=password_reset_tokens_subscriber_registry.register_bus_subscribers,
        register_durable=password_reset_tokens_subscriber_registry.register_durable_handlers,
        nets=password_reset_tokens_subscriber_registry.DURABLE_SUBSCRIBER_NETS,
    ),
    RuntimeModule(
        name="sign_up_tokens",
        register_bus=sign_up_tokens_subscriber_registry.register_bus_subscribers,
        register_durable=sign_up_tokens_subscriber_registry.register_durable_handlers,
        nets=sign_up_tokens_subscriber_registry.DURABLE_SUBSCRIBER_NETS,
    ),
    RuntimeModule(
        name="notifications",
        register_bus=notifications_subscriber_registry.register_all_notification_bus_subscribers,
        register_durable=notifications_subscriber_registry.register_all_notification_durable_handlers,
        nets=notifications_subscriber_registry.NOTIFICATION_DURABLE_SUBSCRIBER_NETS,
        recurring_jobs=notifications_scheduled_jobs.recurring_jobs,
    ),
    RuntimeModule(
        name="websocket",
        register_realtime=websocket_subscriber_registry.register_realtime_subscribers,
    ),
)


def configure_activity_contributors() -> None:
    """Install activity package contributors from the composition root."""
    activities_contributor_registry.clear()
    for ingestion_contributor in (
        activity_laps_integration.ingestion_contributor(),
        activity_sets_integration.ingestion_contributor(),
        activity_streams_integration.ingestion_contributor(),
        activity_workout_steps_integration.ingestion_contributor(),
    ):
        activities_contributor_registry.register_activity_ingestion(ingestion_contributor)
    activities_contributor_registry.register_file_ingestion(
        activity_exercise_titles_integration.ingestion_contributor()
    )
    for profile_contributor in (
        activity_laps_integration.profile_contributor(),
        activity_sets_integration.profile_contributor(),
        activity_streams_integration.profile_contributor(),
        activity_workout_steps_integration.profile_contributor(),
        activity_media_integration.profile_contributor(),
    ):
        activities_contributor_registry.register_profile_activity(profile_contributor)
    activities_contributor_registry.register_profile_global(
        activity_exercise_titles_integration.profile_global_contributor()
    )
    activities_contributor_registry.register_thumbnail_url_resolver(activity_thumbnail_integration.thumbnail_url)


def configure_gear_contributors() -> None:
    """Install the readers the gears namespace asks the activities and component packages to answer."""
    gears_contributor_registry.register(
        gears_contributors.GearReaders(
            usage=activity_integration.get_gear_usage_totals,
            usage_by_window=activity_integration.get_gear_usage_totals_by_window,
            components_cost=gear_components_integration.get_gear_components_total_cost,
            clear_activities_gear=activity_integration.clear_activities_gear,
        )
    )


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register bus subscribers from every installed module.

    On the in-process bus (``memory://``) subscribers would run inside the
    publishing request, so they are deferred to a background pool. A Redis bus
    already delivers on its own consumer thread, and acknowledges after the
    handler returns, so it is left alone.
    """
    in_process = core_config.settings.resolved_events_uri.startswith("memory://")
    target = _DeferredSubscriptions(events) if in_process else events
    for module in MODULES:
        if module.register_bus is not None:
            module.register_bus(target)  # type: ignore[arg-type]


def register_realtime_subscribers(realtime: RealtimeProvider) -> None:
    """Subscribe the process to the realtime hint channel from every installed module.

    Only the API calls this: the worker holds no sockets and just publishes.
    """
    for module in MODULES:
        if module.register_realtime is not None:
            module.register_realtime(realtime)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register durable handlers from every installed module."""
    for module in MODULES:
        if module.register_durable is not None:
            module.register_durable(registry)


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Collect recurring jobs from every installed module."""
    return tuple(job for module in MODULES if module.recurring_jobs is not None for job in module.recurring_jobs())


def startup_tasks() -> tuple[StartupTask, ...]:
    """Collect best-effort startup tasks from every installed module."""
    return tuple(task for module in MODULES for task in module.startup_tasks)


def _load_mail_settings() -> jasil_settings.MailSettings:
    """Read the operator-edited mail settings for the substrate to apply.

    Reads and maps only: the substrate validates the result and decides what a failed
    read or an invalid configuration means.

    Returns:
        The stored mail settings; unset when mail is disabled.
    """
    with core_database.SessionLocal() as db:
        return core_mail.to_mail_settings(server_settings_integration.get_mail_config(db))


def _load_geocoding_settings() -> jasil_settings.GeocodingSettings:
    """Read the operator-edited geocoding settings for the substrate to apply.

    Reads and maps only: the substrate validates the result and decides what a failed
    read or an unusable configuration means.

    Returns:
        The stored geocoding settings; unset when the settings are unavailable.
    """
    with core_database.SessionLocal() as db:
        return core_geocoding.to_geocoding_settings(server_settings_integration.get_geocoding_config(db))


def _cached[T](load: Callable[[], T]) -> Callable[[], T]:
    """Cache a settings loader for a few seconds in this process.

    The substrate asks for the settings on every send and every lookup; without this each
    call would open a database session. A failed load is not cached. Another replica's
    change is seen within ``_SETTINGS_CACHE_SECONDS``.

    Args:
        load: The loader to cache.

    Returns:
        A loader that reloads at most once per ``_SETTINGS_CACHE_SECONDS``.
    """
    lock = threading.Lock()
    cached: tuple[float, T] | None = None

    def read() -> T:
        nonlocal cached
        with lock:
            now = time.monotonic()
            if cached is None or now - cached[0] >= _SETTINGS_CACHE_SECONDS:
                cached = (now, load())
            return cached[1]

    return read


def runtime_sources() -> jasil_settings.RuntimeSources:
    """Return the callables the substrate uses to read operator-edited settings at runtime.

    Returns:
        The runtime sources, shared by the API and the standalone worker.
    """
    return jasil_settings.RuntimeSources(mail=_cached(_load_mail_settings), geocoding=_cached(_load_geocoding_settings))
