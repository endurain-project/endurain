"""Application composition for installed module runtime contributions."""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import jasil.settings as jasil_settings
from jasil.events import Event
from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider, RealtimeProvider

import core.config as core_config
import core.database as core_database
import core.geocoding as core_geocoding
import core.local_pool as core_local_pool
import core.logger as core_logger
import core.mail as core_mail
import core.scheduler as core_scheduler
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.subscriber_registry as activity_subscriber_registry
import modules.activities.activity_exercise_titles.integration_service as activity_exercise_titles_integration
import modules.activities.activity_file_storage.constants as activity_file_storage_constants
import modules.activities.activity_file_storage.scheduled_jobs as activity_file_storage_scheduled_jobs
import modules.activities.activity_file_storage.subscriber_registry as activity_file_storage_subscriber_registry
import modules.activities.activity_geocoding.scheduled_jobs as activity_geocoding_scheduled_jobs
import modules.activities.activity_geocoding.subscriber_registry as activity_geocoding_subscriber_registry
import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.activities.activity_ingestion.scheduled_jobs as activity_ingestion_scheduled_jobs
import modules.activities.activity_ingestion.subscriber_registry as activity_ingestion_subscriber_registry
import modules.activities.activity_laps.integration_service as activity_laps_integration
import modules.activities.activity_media.constants as activity_media_constants
import modules.activities.activity_media.integration_service as activity_media_integration
import modules.activities.activity_media.scheduled_jobs as activity_media_scheduled_jobs
import modules.activities.activity_media.subscriber_registry as activity_media_subscriber_registry
import modules.activities.activity_sets.integration_service as activity_sets_integration
import modules.activities.activity_streams.integration_service as activity_streams_integration
import modules.activities.activity_thumbnail.constants as activity_thumbnail_constants
import modules.activities.activity_thumbnail.integration_service as activity_thumbnail_integration
import modules.activities.activity_thumbnail.scheduled_jobs as activity_thumbnail_scheduled_jobs
import modules.activities.activity_thumbnail.subscriber_registry as activity_thumbnail_subscriber_registry
import modules.activities.activity_workout_steps.integration_service as activity_workout_steps_integration
import modules.activities.contributor_registry as activities_contributor_registry
import modules.auth.authentication.subscriber_registry as authentication_subscriber_registry
import modules.auth.identity_provider_link_tokens.scheduled_jobs as identity_provider_link_tokens_scheduled_jobs
import modules.auth.identity_providers.subscriber_registry as identity_providers_subscriber_registry
import modules.auth.oauth_state.scheduled_jobs as oauth_state_scheduled_jobs
import modules.auth.onboarding.scheduled_jobs as onboarding_scheduled_jobs
import modules.auth.password_reset_tokens.scheduled_jobs as password_reset_tokens_scheduled_jobs
import modules.auth.password_reset_tokens.subscriber_registry as password_reset_tokens_subscriber_registry
import modules.auth.rotated_refresh_tokens.scheduled_jobs as rotated_refresh_tokens_scheduled_jobs
import modules.auth.sessions.scheduled_jobs as auth_sessions_scheduled_jobs
import modules.auth.sign_up_tokens.scheduled_jobs as sign_up_tokens_scheduled_jobs
import modules.auth.sign_up_tokens.subscriber_registry as sign_up_tokens_subscriber_registry
import modules.garmin.integration_service as garmin_integration
import modules.garmin.scheduled_jobs as garmin_scheduled_jobs
import modules.garmin.subscriber_registry as garmin_subscriber_registry
import modules.gears.contributor_registry as gears_contributor_registry
import modules.gears.contributors as gears_contributors
import modules.gears.gear_components.integration_service as gear_components_integration
import modules.notifications.scheduled_jobs as notifications_scheduled_jobs
import modules.notifications.subscriber_registry as notifications_subscriber_registry
import modules.server_settings.constants as server_settings_constants
import modules.server_settings.integration_service as server_settings_integration
import modules.strava.integration_service as strava_integration
import modules.strava.subscriber_registry as strava_subscriber_registry
import modules.users.contributor_registry as users_contributor_registry
import modules.users.contributors as users_contributors
import modules.users.users.constants as users_constants
import modules.users.users.integration_service as users_integration
import modules.users.users.scheduled_jobs as users_scheduled_jobs
import modules.users.users.subscriber_registry as users_subscriber_registry
import modules.users.users_profile.constants as users_profile_constants
import modules.users.users_profile.integration_service as users_profile_integration
import modules.users.users_profile.scheduled_jobs as users_profile_scheduled_jobs
import modules.users.users_profile.subscriber_registry as users_profile_subscriber_registry
import modules.websocket.subscriber_registry as websocket_subscriber_registry

logger = core_logger.get_logger(__name__)

#: How long the mail and geocoding settings are reused before the database is read again.
_SETTINGS_CACHE_SECONDS = 5.0

# Small on purpose: derived work (thumbnails, cleanup, notifications) must not
# compete with request threads for the process. A subscriber past the queue bound is
# dropped and left to its reconciliation net, so a burst cannot grow the queue without limit.
_deferred_pool = core_local_pool.BoundedPool("event-subscriber", workers=2, max_pending=500)


def shutdown_deferred_subscribers() -> None:
    """Stop the subscriber pool without waiting; queued work is repaired by the reconciliation nets."""
    _deferred_pool.shutdown()


def shutdown_module_pools() -> None:
    """Stop the subscriber pool and every in-process pool an installed module declares.

    Each entry point calls this one function, so a pool a module adds is released wherever the module runs.
    """
    shutdown_deferred_subscribers()
    for module in MODULES:
        if module.shutdown is not None:
            module.shutdown()


class _DeferredSubscriptions:
    """Event-bus facade that runs each subscriber on a background pool.

    The in-process bus calls subscribers inline, so a request that publishes
    would wait for every subscriber (map tiles, storage deletes, notifications).
    Handlers registered through this facade are queued instead, and run with the
    publisher's context so the request id still correlates their logs. Everything but
    ``subscribe`` is the wrapped bus's own, so the facade is an ``EventBusProvider`` wherever
    a module's registration expects one.
    """

    def __init__(self, events: EventBusProvider) -> None:
        self._events = events

    def publish(self, event: Event) -> None:
        """Publish an event on the wrapped bus.

        Args:
            event: The event to publish.
        """
        self._events.publish(event)

    def start(self) -> None:
        """Start the wrapped bus."""
        self._events.start()

    def stop(self) -> None:
        """Stop the wrapped bus."""
        self._events.stop()

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Subscribe a handler that runs off the publishing thread.

        Args:
            event_type: The event channel.
            handler: The subscriber to run.
        """

        def deferred(event) -> None:
            try:
                _deferred_pool.submit(handler, event)
            except core_local_pool.PoolFullError:
                logger.warning(
                    "Dropped an event subscriber: the subscriber pool is full; its reconciliation net repairs it",
                    extra=core_logger.context(handler=handler.__name__, event_type=event_type),
                )

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
    lock_name: str | None = None

    def run(self) -> None:
        """Run the task, holding its distributed lock when it declares one.

        A replica that does not get the lock skips the task, so a purge every replica starts at once runs once.
        """
        if self.lock_name is None:
            self.func()
        else:
            core_scheduler.run_locked_job(self.lock_name, self.func)


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
    #: Stops the in-process pools the module runs work on; a no-op when it never started one.
    shutdown: Callable[[], None] | None = None


MODULES: tuple[RuntimeModule, ...] = (
    RuntimeModule(
        name="authentication",
        register_bus=authentication_subscriber_registry.register_bus_subscribers,
    ),
    RuntimeModule(
        name="activity",
        register_durable=activity_subscriber_registry.register_durable_handlers,
        nets=activity_subscriber_registry.DURABLE_SUBSCRIBER_NETS,
        shutdown=activity_integration.shutdown_bulk_edit_pool,
    ),
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
                "fail_orphaned_local_refreshes",
                "Failing provider refreshes lost with the previous process",
                activity_ingestion_scheduled_jobs.fail_orphaned_local_refreshes,
            ),
            StartupTask(
                "queue_provider_refreshes",
                "Queueing a provider activity refresh for every linked user",
                activity_ingestion_scheduled_jobs.schedule_provider_refresh,
            ),
        ),
        shutdown=activity_ingestion_integration.shutdown_background_ingestion,
    ),
    RuntimeModule(
        name="oauth_state",
        recurring_jobs=oauth_state_scheduled_jobs.recurring_jobs,
        startup_tasks=(
            StartupTask(
                "purge_expired_oauth_states",
                "Purging expired OAuth states",
                oauth_state_scheduled_jobs.delete_expired_oauth_states_from_db,
                lock_name=oauth_state_scheduled_jobs.PURGE_LOCK_NAME,
            ),
        ),
    ),
    RuntimeModule(name="sessions", recurring_jobs=auth_sessions_scheduled_jobs.recurring_jobs),
    RuntimeModule(name="rotated_refresh_tokens", recurring_jobs=rotated_refresh_tokens_scheduled_jobs.recurring_jobs),
    RuntimeModule(
        name="identity_providers",
        register_bus=identity_providers_subscriber_registry.register_bus_subscribers,
        register_durable=identity_providers_subscriber_registry.register_durable_handlers,
        nets=identity_providers_subscriber_registry.DURABLE_SUBSCRIBER_NETS,
    ),
    RuntimeModule(
        name="identity_provider_link_tokens",
        recurring_jobs=identity_provider_link_tokens_scheduled_jobs.recurring_jobs,
        startup_tasks=(
            StartupTask(
                "purge_expired_identity_provider_link_tokens",
                "Purging expired identity-provider link tokens",
                identity_provider_link_tokens_scheduled_jobs.delete_expired_tokens_from_db,
                lock_name=identity_provider_link_tokens_scheduled_jobs.PURGE_LOCK_NAME,
            ),
        ),
    ),
    RuntimeModule(
        name="onboarding",
        startup_tasks=(
            StartupTask(
                "issue_onboarding_token",
                "Checking whether first-run onboarding is required",
                onboarding_scheduled_jobs.issue_onboarding_token_if_needed,
            ),
        ),
    ),
    RuntimeModule(
        name="password_reset_tokens",
        register_bus=password_reset_tokens_subscriber_registry.register_bus_subscribers,
        register_durable=password_reset_tokens_subscriber_registry.register_durable_handlers,
        nets=password_reset_tokens_subscriber_registry.DURABLE_SUBSCRIBER_NETS,
        recurring_jobs=password_reset_tokens_scheduled_jobs.recurring_jobs,
        startup_tasks=(
            StartupTask(
                "purge_expired_password_reset_tokens",
                "Purging expired password reset tokens",
                password_reset_tokens_scheduled_jobs.delete_expired_tokens_from_db,
                lock_name=password_reset_tokens_scheduled_jobs.PURGE_LOCK_NAME,
            ),
        ),
    ),
    RuntimeModule(
        name="sign_up_tokens",
        register_bus=sign_up_tokens_subscriber_registry.register_bus_subscribers,
        register_durable=sign_up_tokens_subscriber_registry.register_durable_handlers,
        nets=sign_up_tokens_subscriber_registry.DURABLE_SUBSCRIBER_NETS,
        recurring_jobs=sign_up_tokens_scheduled_jobs.recurring_jobs,
        startup_tasks=(
            StartupTask(
                "purge_expired_sign_up_tokens",
                "Purging expired sign-up tokens",
                sign_up_tokens_scheduled_jobs.delete_expired_tokens_from_db,
                lock_name=sign_up_tokens_scheduled_jobs.PURGE_LOCK_NAME,
            ),
        ),
    ),
    RuntimeModule(
        name="notifications",
        register_bus=notifications_subscriber_registry.register_bus_subscribers,
        register_durable=notifications_subscriber_registry.register_durable_handlers,
        nets=notifications_subscriber_registry.DURABLE_SUBSCRIBER_NETS,
        recurring_jobs=notifications_scheduled_jobs.recurring_jobs,
    ),
    RuntimeModule(
        name="users",
        register_durable=users_subscriber_registry.register_durable_handlers,
        nets=users_subscriber_registry.DURABLE_SUBSCRIBER_NETS,
        recurring_jobs=users_scheduled_jobs.recurring_jobs,
        shutdown=users_integration.shutdown_deletion_pool,
    ),
    RuntimeModule(
        name="users_profile",
        register_bus=users_profile_subscriber_registry.register_bus_subscribers,
        register_durable=users_profile_subscriber_registry.register_durable_handlers,
        nets=users_profile_subscriber_registry.DURABLE_SUBSCRIBER_NETS,
        recurring_jobs=users_profile_scheduled_jobs.recurring_jobs,
        shutdown=users_profile_integration.shutdown_transfer_pool,
    ),
    RuntimeModule(
        name="garmin",
        register_durable=garmin_subscriber_registry.register_durable_handlers,
        nets=garmin_subscriber_registry.DURABLE_SUBSCRIBER_NETS,
        recurring_jobs=garmin_scheduled_jobs.recurring_jobs,
        startup_tasks=(
            StartupTask(
                "retrieve_recent_garmin_health",
                "Scheduling the last day health stats pull from Garmin Connect",
                garmin_scheduled_jobs.schedule_recent_health,
            ),
        ),
        shutdown=garmin_integration.shutdown_pools,
    ),
    RuntimeModule(
        name="strava",
        register_durable=strava_subscriber_registry.register_durable_handlers,
        nets=strava_subscriber_registry.DURABLE_SUBSCRIBER_NETS,
        shutdown=strava_integration.shutdown_pools,
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


def configure_application() -> None:
    """Install everything the API and the standalone worker both need before they run work.

    The contributors and erasers the namespaces ask composition for, and the activity providers
    ingestion pulls from. A job claimed by the worker resolves the same seams a request does, so a
    registration made by one entrypoint and not the other would silently do nothing wherever it runs;
    one call from both is what keeps them from drifting.
    """
    configure_activity_contributors()
    configure_gear_contributors()
    configure_user_contributors()
    strava_integration.register_activity_provider()
    garmin_integration.register_activity_provider()


def configure_user_contributors() -> None:
    """Install the erasures the users namespace asks the activities and profile modules to answer."""
    users_contributor_registry.register(
        users_contributors.UserErasers(
            delete_activities=activity_integration.delete_activities_batch_for_user,
            delete_staged_files=users_profile_integration.delete_staged_transfers,
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
            module.register_bus(target)


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


def storage_plain_areas() -> frozenset[str]:
    """Return the storage areas the local backend keeps as browsable files.

    Every area the application owns is listed, so on ``local://`` the whole blob
    store is ordinary files under ``{data_dir}/{area}/{key}`` rather than JASIL's
    hashed layout. S3 ignores the set and behaves identically for every area.

    Returns:
        The areas whose local objects live at ``{data_dir}/{area}/{key}``.
    """
    return frozenset(
        {
            activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA,
            activity_ingestion_constants.BULK_IMPORT_ERROR_STORAGE_AREA,
            activity_media_constants.MEDIA_STORAGE_AREA,
            activity_thumbnail_constants.THUMBNAIL_STORAGE_AREA,
            server_settings_constants.LOGIN_PHOTO_STORAGE_AREA,
            users_constants.USER_IMAGE_STORAGE_AREA,
            users_profile_constants.EXPORT_STAGING_AREA,
            users_profile_constants.IMPORT_STAGING_AREA,
        }
    )
