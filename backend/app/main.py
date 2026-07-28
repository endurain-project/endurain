import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import cast

from alembic.config import Config

from alembic import command

# Silence stravalib token warnings as early as
# possible: this env var is consulted at import time by
# stravalib, so it must be set before any module that
# transitively imports it runs.
os.environ["SILENCE_TOKEN_WARNINGS"] = "TRUE"

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.sessions import SessionMiddleware

import core.config as core_config
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.middleware as core_middleware
import core.middleware_request_id as core_middleware_request_id
import core.migrations as core_migrations
import core.network as core_network
import core.rate_limit as core_rate_limit
import core.scheduler as core_scheduler
import infra.async_bridge as platform_async_bridge
import infra.capabilities as platform_capabilities
import infra.container as platform_container
import infra.jobs.registry as jobs_registry
import infra.jobs.service as jobs_service
import infra.runtime as platform_runtime
import modules.activities.activity_ingestion.background as activity_ingestion_background
import modules.activities.subscriber_registry as activity_subscriber_registry
import modules.auth.identity_providers.link_tokens.utils as idp_link_token_utils
import modules.auth.oauth_state.utils as oauth_state_utils
import modules.auth.password_reset_tokens.utils as password_reset_tokens_utils
import modules.auth.sign_up_tokens.utils as sign_up_tokens_utils
import modules.auth.utils as auth_utils
import modules.followers.subscribers as followers_subscribers
import modules.garmin.activity_utils as garmin_activity_utils
import modules.garmin.health_utils as garmin_health_utils
import modules.server_settings.schema as server_settings_schema
import modules.server_settings.utils as server_settings_utils
import modules.strava.activity_utils as strava_activity_utils
import modules.strava.utils as strava_utils
from api import router as api_router
from core.database import SessionLocal
from core.database import engine as core_db_engine

logger = core_logger.get_logger(__name__)

_DEPLOYED_ENVIRONMENTS = {"production", "demo"}


def _safe_run[T, **P](
    label: str,
    func: Callable[P, T],
    *args: P.args,
    **kwargs: P.kwargs,
) -> T | None:
    """Invoke a startup task, isolating its failure.

    Logs the exception type (not the raw message, to
    avoid leaking sensitive context) so a single
    misbehaving integration cannot abort backend
    startup.
    """
    try:
        return func(*args, **kwargs)
    except Exception as err:
        logger.error(f"Startup task '{label}' failed: {type(err).__name__}", exc_info=err)
        return None


async def _safe_run_async[T, **P](
    label: str,
    coro_func: Callable[P, Awaitable[T]],
    *args: P.args,
    **kwargs: P.kwargs,
) -> T | None:
    """Async variant of :func:`_safe_run`."""
    try:
        return await coro_func(*args, **kwargs)
    except Exception as err:
        logger.error(f"Startup task '{label}' failed: {type(err).__name__}", exc_info=err)
        return None


def _run_alembic_migrations() -> None:
    """Run Alembic upgrade to head.

    Critical: failure here aborts startup because the
    application cannot guarantee schema correctness.
    """
    alembic_cfg = Config("alembic.ini")
    # Disable Alembic's own logger configuration to
    # avoid conflicts with FastAPI / our main logger.
    alembic_cfg.attributes["configure_logger"] = False
    command.upgrade(alembic_cfg, "head")


def _refresh_strava_tokens() -> None:
    """Refresh persisted Strava OAuth tokens."""
    strava_utils.refresh_strava_tokens(True)


async def _retrieve_recent_garmin_activities() -> None:
    """Backfill the last day of Garmin Connect activities."""
    await garmin_activity_utils.retrieve_garminconnect_users_activities_for_days(1)


async def _retrieve_recent_strava_activities() -> None:
    """Backfill the last day of Strava activities."""
    await strava_activity_utils.retrieve_strava_users_activities_for_days(
        1,
        True,
    )


async def _retrieve_recent_garmin_health() -> None:
    """Backfill the last day of Garmin Connect health stats."""
    await garmin_health_utils.retrieve_garminconnect_users_health_for_days(1)


def _purge_expired_tokens() -> None:
    """Sweep expired/invalid auth-related tokens from the DB."""
    password_reset_tokens_utils.delete_invalid_tokens_from_db()
    sign_up_tokens_utils.delete_invalid_tokens_from_db()
    oauth_state_utils.delete_expired_oauth_states_from_db()
    idp_link_token_utils.delete_idp_link_expired_tokens_from_db()


def _generate_missing_thumbnails() -> None:
    """Queue map-thumbnail generation for activities missing one.

    Schedules a one-shot job on the background scheduler instead of
    running the (potentially heavy) generation inline, so it cannot
    block lifespan startup and delay the server from accepting
    connections.
    """
    core_scheduler.schedule_missing_thumbnail_generation()


def _backfill_missing_hr_zones() -> None:
    """Queue HR-zone backfill for streams missing zone percentages.

    Schedules a one-shot job on the background scheduler (the reconciliation net
    for the activity.created HR-zone subscriber) instead of running the backfill
    inline, so it cannot block lifespan startup.
    """
    core_scheduler.schedule_missing_hr_zone_backfill()


def _backfill_missing_locations() -> None:
    """Queue reverse-geocoding backfill for activities missing a location.

    Schedules a one-shot job on the background scheduler (the reconciliation net
    for the activity.created geocoding subscriber) instead of running the
    network-bound backfill inline, so it cannot block lifespan startup.
    """
    core_scheduler.schedule_missing_location_backfill()


def _init_allowed_tile_domains(fastapi_app: FastAPI) -> None:
    """Populate ``app.state.allowed_tile_domains`` for CSP.

    Falls back to the built-in default provider list if
    the database lookup fails so the application can
    still serve requests with a safe CSP.
    """
    with SessionLocal() as db:
        try:
            fastapi_app.state.allowed_tile_domains = server_settings_utils.get_allowed_tile_domains(db)
            allowed_tile_domains = fastapi_app.state.allowed_tile_domains
            logger.info(f"Allowed tile domains: {allowed_tile_domains}", extra=core_logger.context(console=True))
        except Exception as err:
            logger.error(f"Error initializing tile domains, using defaults: {type(err).__name__}", exc_info=err)
            # Fallback to built-in providers so CSP
            # remains restrictive but functional.
            fastapi_app.state.allowed_tile_domains = server_settings_schema.DEFAULT_ALLOWED_TILE_DOMAINS.copy()


async def _resolve_trusted_proxy_hostnames() -> dict[str, list[str]]:
    """Refresh TRUSTED_PROXIES hostnames at startup.

    Called during Phase 2 of startup (best-effort). The same
    helper is reused by request-time trust checks to avoid stale
    Docker container IPs after proxy-only restarts.

    Returns:
        Dictionary mapping hostnames to their resolved IP lists.
        Empty dict if no hostnames are configured or all fail.
    """
    return core_network.refresh_trusted_proxy_hostnames(
        force=True,
        log_success=True,
    )


def _log_capability_report() -> None:
    """Log how each infrastructure capability is wired for this deployment.

    Renders the resolved backend for state, storage, events, lock, and clock so
    the effective wiring is visible at boot. Purely observational; the fatal
    consistency checks live in ``core.config``
    (``Settings._enforce_deployment_topology``).
    """
    settings = core_config.settings
    state_label = "STATE_URI" if settings.STATE_URI else "REDIS_URL" if settings.REDIS_URL else "profile default"
    storage_uri = settings.resolved_storage_uri
    storage_backend = "s3" if storage_uri.startswith("s3://") else "local"
    storage_source = "STORAGE_URI" if settings.STORAGE_URI else "profile default"
    events_uri = settings.resolved_events_uri
    events_backend = "redis" if events_uri.startswith(("redis://", "rediss://", "unix://")) else "in-process"
    events_source = "EVENTS_URI" if settings.EVENTS_URI else "REDIS_URL" if settings.REDIS_URL else "profile default"
    lock_uri = settings.resolved_lock_uri
    lock_backend = "pg" if lock_uri.startswith("postgres-advisory://") else "none"
    lock_source = "LOCK_URI" if settings.LOCK_URI else "profile default"
    report = platform_capabilities.build_capability_report(
        profile=settings.DEPLOYMENT_PROFILE,
        web_workers=settings.WEB_WORKERS,
        primary_state=platform_capabilities.StateSource(state_label, settings.resolved_state_uri),
        storage_backend=storage_backend,
        storage_source=storage_source,
        events_backend=events_backend,
        events_source=events_source,
        lock_backend=lock_backend,
        lock_source=lock_source,
    )
    # Emit each line as its own record so every line carries the standard log
    # prefix; a single multi-line message only prefixes the first line.
    logger.info("Deployment capability report:", extra=core_logger.context(console=True))
    for line in report.render().splitlines():
        logger.info(line, extra=core_logger.context(console=True))


async def startup_event(fastapi_app: FastAPI) -> None:
    """Run startup tasks in well-defined phases.

    Phase 1 (critical): schema migrations and the
    background scheduler. Failure aborts startup.

    Phase 2 (best-effort): third-party syncs, token
    purges, thumbnail generation, and CSP tile-domain
    initialisation. Each task is isolated so a single
    failure cannot prevent the backend from serving
    requests.
    """
    logger.info(f"Backend startup event - {core_config.API_VERSION}", extra=core_logger.context(console=True))

    # Observational capability report (reflects today's effective wiring).
    _log_capability_report()

    # Build the platform substrate (providers + backends) and attach it to app state.
    platform = platform_container.build_platform(core_config.settings)
    fastapi_app.state.platform = platform

    # Publish it process-wide so background work (scheduler, Garmin login thread)
    # that has no request can resolve providers via infra.runtime.
    platform_runtime.set_active_platform(platform)

    # Capture the running event loop so synchronous code (sync routes in the
    # threadpool, in-process event subscribers) can dispatch async I/O — e.g. a
    # websocket push — back onto it via infra.async_bridge.
    platform_async_bridge.capture_running_loop()

    # Register every activities event-bus subscriber before starting the bus, and
    # every activities durable-job handler on the registry — both via the single
    # shared surface in activities.subscriber_registry so the API and the standalone
    # worker can never drift. The bus subscribers (thumbnail, notification,
    # HR-zone, geocoding) react to activity.created / activity.deleted; the durable
    # handlers are the same set keyed by stable subscriber id (harmless when durable
    # jobs are off, retryable per-subscriber when on). Each durable subscriber that
    # writes durable derived state declares a reconciliation net (scheduled backfill)
    # in that module.
    activity_subscriber_registry.register_all_activity_bus_subscribers(platform.events)
    activity_subscriber_registry.register_all_activity_durable_handlers(jobs_registry.registry)
    followers_subscribers.register_follower_notification_subscribers(platform.events)

    # Start the event bus. No-op for the in-process bus (local); starts the
    # Redis Streams consumer thread in distributed mode.
    platform.events.start()

    # Phase 1: critical pre-flight tasks.
    _run_alembic_migrations()
    await core_migrations.check_migrations()
    core_scheduler.start_scheduler()

    # Durable job processing (opt-in). Start the in-process worker that drains
    # processing_jobs and register the outbox relay + lease reaper on the
    # scheduler. The relay and reaper run on every replica (coordinated by
    # SELECT ... FOR UPDATE SKIP LOCKED plus the idempotent job fan-out), so no
    # single-runner lock is needed. Inert unless JOBS_ENABLED. The in-process
    # worker can be turned off (JOBS_RUN_IN_PROCESS_WORKER=false) when running
    # dedicated worker processes; the API still relays and reaps.
    if core_config.settings.JOBS_ENABLED:
        if core_config.settings.JOBS_RUN_IN_PROCESS_WORKER:
            jobs_service.start_job_worker()
        else:
            logger.warning(
                "JOBS_ENABLED with JOBS_RUN_IN_PROCESS_WORKER=false: this API "
                "process will not drain the durable-job queue. Run a dedicated "
                "worker (APP_ROLE=worker) or jobs will accumulate unprocessed.",
                extra=core_logger.context(console=True),
            )
        jobs_service.schedule_job_maintenance(core_scheduler.scheduler)
    elif core_config.settings.resolved_events_uri.startswith(("redis://", "rediss://", "unix://")):
        # A deployment on the Redis Streams bus (distributed, or multi-worker) with
        # durable jobs off delivers derived work best-effort: the bus has no
        # per-subscriber retry and no recovery of a crashed consumer's in-flight
        # events. This is advisory, NOT fatal — a subscriber with its own
        # reconciliation net (like the thumbnail backfill) is safe without durable
        # jobs, and JOBS_ENABLED is orthogonal to the capability wiring the boot
        # fail-fast validates, so it must not block startup of a valid deployment.
        logger.warning(
            "JOBS_ENABLED is false while the event bus is Redis Streams "
            "(distributed / multi-worker): derived work is delivered best-effort, "
            "with no per-subscriber retry and no recovery of a crashed consumer's "
            "in-flight events. Enable JOBS_ENABLED for durable, retryable delivery, "
            "or ensure every event subscriber has a reconciliation net (e.g. the "
            "thumbnail backfill).",
            extra=core_logger.context(console=True),
        )

    # Phase 2: best-effort background syncs and clean-up.
    logger.info("Refreshing Strava tokens on startup", extra=core_logger.context(console=True))
    _safe_run("refresh_strava_tokens", _refresh_strava_tokens)

    logger.info(
        "Retrieving last day activities from Garmin Connect on startup", extra=core_logger.context(console=True)
    )
    await _safe_run_async("retrieve_recent_garmin_activities", _retrieve_recent_garmin_activities)

    logger.info("Retrieving last day activities from Strava on startup", extra=core_logger.context(console=True))
    await _safe_run_async("retrieve_recent_strava_activities", _retrieve_recent_strava_activities)

    logger.info(
        "Retrieving last day health stats from Garmin Connect on startup", extra=core_logger.context(console=True)
    )
    await _safe_run_async(
        "retrieve_recent_garmin_health",
        _retrieve_recent_garmin_health,
    )

    logger.info(
        "Purging expired tokens (password reset, sign-up, OAuth state, IdP link)",
        extra=core_logger.context(console=True),
    )
    _safe_run("purge_expired_tokens", _purge_expired_tokens)

    logger.info("Scheduling missing activity map thumbnail generation", extra=core_logger.context(console=True))
    _safe_run("generate_missing_thumbnails", _generate_missing_thumbnails)

    logger.info("Scheduling missing HR-zone backfill", extra=core_logger.context(console=True))
    _safe_run("backfill_missing_hr_zones", _backfill_missing_hr_zones)

    logger.info("Scheduling missing activity location backfill", extra=core_logger.context(console=True))
    _safe_run("backfill_missing_locations", _backfill_missing_locations)

    logger.info(
        "Initializing allowed tile domains for Content Security Policy", extra=core_logger.context(console=True)
    )
    _init_allowed_tile_domains(fastapi_app)

    logger.info("Resolving TRUSTED_PROXIES hostnames", extra=core_logger.context(console=True))
    await _safe_run_async("resolve_trusted_proxy_hostnames", _resolve_trusted_proxy_hostnames)

    logger.info(
        f"Allowed trusted proxies: {core_config.settings.TRUSTED_PROXIES}", extra=core_logger.context(console=True)
    )
    if core_config.settings._resolved_trusted_proxy_ips:
        logger.info(
            f"Resolved trusted proxy IPs: {sorted(core_config.settings._resolved_trusted_proxy_ips)}",
            extra=core_logger.context(console=True),
        )


def shutdown_event(fastapi_app: FastAPI) -> None:
    """Stop the event bus and scheduler and release DB resources on shutdown."""
    logger.info("Backend shutdown event", extra=core_logger.context(console=True))

    # Stop the event bus consumer (no-op for the in-process bus; joins the Redis
    # Streams consumer thread in distributed mode). Guarded because startup may
    # have failed before the platform was attached.
    platform = getattr(fastapi_app.state, "platform", None)
    if platform is not None:
        platform.events.stop()

    # Stop the in-process durable-job worker (safe if it was never started).
    jobs_service.stop_job_worker()

    # Stop the bulk-import background pool (no-op when it was never started, i.e.
    # when durable jobs handle imports instead).
    activity_ingestion_background.shutdown()

    core_scheduler.stop_scheduler()

    # Clear the captured event loop; nothing may dispatch onto it after shutdown.
    platform_async_bridge.set_main_loop(None)

    # Dispose the SQLAlchemy engine so all pooled
    # psycopg connections are closed deterministically.
    try:
        core_db_engine.dispose()
    except Exception as err:
        logger.error(
            f"Error disposing database engine on shutdown: {type(err).__name__}",
            extra=core_logger.context(console=True),
        )


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown."""
    await startup_event(fastapi_app)
    try:
        yield
    finally:
        shutdown_event(fastapi_app)


def create_app() -> FastAPI:
    """Build, configure, and return the FastAPI app.

    Pre-flight: reject retired env vars, validate required
    env vars, ensure data directories exist, and configure
    the main logger so every subsequent log line is
    captured by the environment-appropriate handler.
    """
    # Pre-flight checks that must run before the app is
    # constructed: retired and required environment
    # variables and filesystem layout. Logger setup must
    # happen after config validation so log routing
    # reflects the validated settings.
    core_config.check_deprecated_env_vars()
    core_config.check_required_env_vars()
    core_config.check_required_dirs()
    core_logger.setup_main_logger()

    is_development = core_config.settings.ENVIRONMENT == "development"
    is_deployed = core_config.settings.ENVIRONMENT in _DEPLOYED_ENVIRONMENTS
    docs_url = f"{core_config.ROOT_PATH}/docs" if is_development else None
    redoc_url = f"{core_config.ROOT_PATH}/redoc" if is_development else None

    # Define the FastAPI object
    fastapi_app = FastAPI(
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=redoc_url,
        title="Endurain",
        summary="Endurain API for the Endurain app",
        version=core_config.API_VERSION,
        license_info={
            "name": core_config.LICENSE_NAME,
            "identifier": core_config.LICENSE_IDENTIFIER,
            "url": core_config.LICENSE_URL,
        },
    )

    # Add session middleware for OAuth state management
    fastapi_app.add_middleware(
        SessionMiddleware,
        secret_key=cast(str, core_config.read_secret("SECRET_KEY")),
        session_cookie="endurain_session",
        max_age=3600,  # 1 hour session timeout
        same_site="lax",
        https_only=is_deployed,
    )

    # Add CORS middleware to allow requests from the frontend
    if is_development:
        cors_allow_origins: list[str] = [
            "http://localhost:8080",
            "http://localhost:5173",
            "http://localhost:5174",
            core_config.settings.ENDURAIN_HOST,
        ]
    else:
        cors_allow_origins = [core_config.settings.ENDURAIN_HOST]

    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Client-Type",
            "X-CSRF-Token",
        ],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    # Add security headers middleware (before CSRF for proper header ordering)
    fastapi_app.add_middleware(core_middleware.SecurityHeadersMiddleware)

    # Add CSRF protection middleware
    fastapi_app.add_middleware(core_middleware.CSRFMiddleware)

    # Add rate limiting
    fastapi_app.state.limiter = core_rate_limit.limiter
    fastapi_app.add_exception_handler(
        core_rate_limit.RateLimitExceeded,
        core_rate_limit.rate_limit_exceeded_handler,  # type: ignore[arg-type]
    )
    fastapi_app.add_exception_handler(
        auth_utils.ClearRefreshTokenCookieHTTPException,
        auth_utils.clear_refresh_token_cookie_exception_handler,  # type: ignore[arg-type]
    )
    # Single API boundary for the transport-agnostic domain errors raised by the
    # application layers (services, ingestion pipeline, file parsers). Those
    # layers no longer import FastAPI to report a failure — this handler owns the
    # status code and renders the same ``{"detail": ...}`` body HTTPException
    # produces, so the client-visible contract is unchanged.
    core_exceptions.register_exception_handlers(fastapi_app)
    fastapi_app.add_middleware(SlowAPIMiddleware)

    # RequestIdMiddleware is added last so it executes
    # first in the request chain, ensuring every log
    # line (including those from other middlewares and
    # error responses) carries an X-Request-ID.
    fastapi_app.add_middleware(
        core_middleware_request_id.RequestIdMiddleware,
    )

    # Static mounts must be registered before the
    # catch-all frontend route included by api_router.
    fastapi_app.mount(
        f"/{core_config.USER_IMAGES_DIR}",
        StaticFiles(directory=core_config.USER_IMAGES_DIR),
        name="user_images",
    )
    fastapi_app.mount(
        f"/{core_config.SERVER_IMAGES_DIR}",
        StaticFiles(directory=core_config.SERVER_IMAGES_DIR),
        name="server_images",
    )
    fastapi_app.mount(
        f"/{core_config.settings.ACTIVITY_MEDIA_DIR}",
        StaticFiles(directory=core_config.settings.ACTIVITY_MEDIA_DIR),
        name="activity_media",
    )
    # NOTE: activity thumbnails are intentionally NOT mounted as public static
    # files. They are served by the token-gated route in
    # modules.activities.activity_thumbnail.router, so the blobs are only
    # reachable with a valid signed URL (visibility-masked per viewer) rather
    # than at a guessable public path.

    # Router files
    fastapi_app.include_router(api_router)

    return fastapi_app


# Create the FastAPI application
app = create_app()
