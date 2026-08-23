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

import jasil.container as platform_container
import jasil.correlation as jasil_correlation
import jasil.jobs.registry as jobs_registry
import jasil.jobs.service as jobs_service
import jasil.lifecycle as jasil_lifecycle
import jasil.runtime as platform_runtime
import jasil.settings as jasil_settings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.sessions import SessionMiddleware

import core.async_bridge as core_async_bridge
import core.config as core_config
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.middleware as core_middleware
import core.middleware_request_id as core_middleware_request_id
import core.migrations as core_migrations
import core.network as core_network
import core.platform_settings as core_platform_settings
import core.problem_details as core_problem_details
import core.rate_limit as core_rate_limit
import core.scheduler as core_scheduler
import module_registry as runtime_module_registry
import modules.activities.activity_ingestion.integration_service as activity_ingestion
import modules.auth.identity_providers.link_tokens.utils as idp_link_token_utils
import modules.auth.oauth_state.utils as oauth_state_utils
import modules.auth.password_reset_tokens.utils as password_reset_tokens_utils
import modules.auth.scheduled_jobs as auth_scheduled_jobs
import modules.auth.sign_up_tokens.utils as sign_up_tokens_utils
import modules.auth.utils as auth_utils
import modules.garmin.activity_utils as garmin_activity_utils
import modules.garmin.health_utils as garmin_health_utils
import modules.garmin.provider_registry as garmin_provider_registry
import modules.garmin.scheduled_jobs as garmin_scheduled_jobs
import modules.server_settings.schema as server_settings_schema
import modules.server_settings.utils as server_settings_utils
import modules.strava.activity_utils as strava_activity_utils
import modules.strava.provider_registry as strava_provider_registry
import modules.strava.scheduled_jobs as strava_scheduled_jobs
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

    # Install the host's configuration and correlation source before anything
    # reads them. The substrate logs its own capability report as it builds.
    substrate_settings = core_platform_settings.build_jasil_settings(core_config.settings)
    jasil_settings.configure(substrate_settings)
    jasil_correlation.configure_provider(lambda: core_middleware_request_id.get_request_id() or None)

    # Build the platform substrate (providers + backends) and attach it to app state.
    platform = platform_container.build_platform(substrate_settings)
    fastapi_app.state.platform = platform

    # Publish it process-wide so background work (scheduler, Garmin login thread)
    # that has no request can resolve providers via jasil.runtime.
    platform_runtime.set_active_platform(platform)

    # Capture the running event loop so synchronous code (sync routes in the
    # threadpool, in-process event subscribers) can dispatch async I/O — e.g. a
    # websocket push — back onto it via core.async_bridge.
    core_async_bridge.capture_running_loop()

    # Configure activity contributors, then register every event-bus subscriber
    # and durable-job handler through the shared app composition root so the API
    # and standalone worker cannot drift. The bus subscribers (thumbnail, notification,
    # HR-zone, geocoding) react to activity.created / activity.deleted; the durable
    # handlers are the same set keyed by stable subscriber id (harmless when durable
    # jobs are off, retryable per-subscriber when on). Each durable subscriber that
    # writes durable derived state declares a reconciliation net (scheduled backfill)
    # in that module.
    runtime_module_registry.configure_activity_contributors()
    runtime_module_registry.register_bus_subscribers(platform.events)
    runtime_module_registry.register_durable_handlers(jobs_registry.registry)
    # Providers register themselves with ingestion; ingestion imports none of
    # them. Must also happen in worker.py, where refresh jobs are claimed.
    strava_provider_registry.register_activity_provider()
    garmin_provider_registry.register_activity_provider()

    # Start the event bus. No-op for the in-process bus (local); starts the
    # Redis Streams consumer thread in distributed mode.
    platform.events.start()

    # Phase 1: critical pre-flight tasks.
    _run_alembic_migrations()
    await core_migrations.check_migrations()
    # The composition root collects each module's own declaration; the scheduler
    # knows how to schedule, never what.
    core_scheduler.start_scheduler(
        [
            *core_scheduler.platform_jobs(),
            *auth_scheduled_jobs.recurring_jobs(),
            *runtime_module_registry.recurring_jobs(),
            *strava_scheduled_jobs.recurring_jobs(),
            *garmin_scheduled_jobs.recurring_jobs(),
        ]
    )

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

    for task in runtime_module_registry.startup_tasks():
        logger.info(task.description, extra=core_logger.context(console=True))
        _safe_run(task.name, task.func)

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

    # Stop the durable-job worker, then release what the platform owns (the bus
    # consumer thread and any shared Redis clients) and unpublish it. That order
    # matters: the worker runs subscribers, and a subscriber that publishes needs
    # the bus still up.
    jasil_lifecycle.shutdown()

    # Stop the bulk-import background pool (no-op when it was never started, i.e.
    # when durable jobs handle imports instead).
    activity_ingestion.shutdown_background_ingestion()

    core_scheduler.stop_scheduler()

    # Clear the captured event loop; nothing may dispatch onto it after shutdown.
    core_async_bridge.set_main_loop(None)

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
    is_development_or_demo = core_config.settings.ENVIRONMENT in {"development", "demo"}
    is_deployed = core_config.settings.ENVIRONMENT in _DEPLOYED_ENVIRONMENTS
    docs_url = f"{core_config.ROOT_PATH}/docs" if is_development_or_demo else None
    redoc_url = f"{core_config.ROOT_PATH}/redoc" if is_development_or_demo else None

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
        allow_headers=list(core_middleware.CORS_ALLOW_HEADERS),
        expose_headers=list(core_middleware.CORS_EXPOSE_HEADERS),
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
    # Keep the generated schema describing the problem documents those handlers
    # emit, rather than FastAPI's defaults.
    core_problem_details.install_problem_schema(fastapi_app)
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
        f"/{core_config.SERVER_IMAGES_DIR}",
        StaticFiles(directory=core_config.SERVER_IMAGES_DIR),
        name="server_images",
    )
    # NOTE: activity thumbnails, activity media and user photos are intentionally
    # NOT mounted as public static files. Each is served by a token-gated route
    # (modules.activities.activity_thumbnail.router,
    # modules.activities.activity_media.public_router,
    # modules.users.users.photo_router), so a blob is only reachable with a valid
    # signed URL handed to a permitted viewer rather than at a guessable path.
    # Server images stay public: they are the login-page branding, needed before
    # anyone is authenticated.

    # Router files
    fastapi_app.include_router(api_router)

    return fastapi_app


# Create the FastAPI application
app = create_app()
