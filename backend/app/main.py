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

import auth.identity_providers.link_tokens.utils as idp_link_token_utils
import auth.oauth_state.utils as oauth_state_utils
import auth.password_reset_tokens.utils as password_reset_tokens_utils
import auth.sign_up_tokens.utils as sign_up_tokens_utils
import auth.utils as auth_utils
import core.config as core_config
import core.logger as core_logger
import core.middleware as core_middleware
import core.middleware_request_id as core_middleware_request_id
import core.migrations as core_migrations
import core.network as core_network
import core.platform.capabilities as platform_capabilities
import core.platform.container as platform_container
import core.platform.runtime as platform_runtime
import core.rate_limit as core_rate_limit
import core.scheduler as core_scheduler
import garmin.activity_utils as garmin_activity_utils
import garmin.health_utils as garmin_health_utils
import server_settings.schema as server_settings_schema
import server_settings.utils as server_settings_utils
import strava.activity_utils as strava_activity_utils
import strava.utils as strava_utils
from core.database import SessionLocal
from core.database import engine as core_db_engine
from core.routes import router as api_router

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
        core_logger.print_to_log(
            f"Startup task '{label}' failed: {type(err).__name__}",
            "error",
            exc=err,
        )
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
        core_logger.print_to_log(
            f"Startup task '{label}' failed: {type(err).__name__}",
            "error",
            exc=err,
        )
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
            core_logger.print_to_log_and_console(f"Allowed tile domains: {allowed_tile_domains}")
        except Exception as err:
            core_logger.print_to_log(
                f"Error initializing tile domains, using defaults: {type(err).__name__}",
                "error",
                exc=err,
            )
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
    core_logger.print_to_log_and_console("Deployment capability report:")
    for line in report.render().splitlines():
        core_logger.print_to_log_and_console(line)


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
    core_logger.print_to_log_and_console(f"Backend startup event - {core_config.API_VERSION}")

    # Observational capability report (reflects today's effective wiring).
    _log_capability_report()

    # Build the platform substrate (providers + backends) and attach it to app state.
    platform = platform_container.build_platform(core_config.settings)
    fastapi_app.state.platform = platform

    # Publish it process-wide so background work (scheduler, Garmin login thread)
    # that has no request can resolve providers via core.platform.runtime.
    platform_runtime.set_active_platform(platform)

    # Start the event bus. No-op for the in-process bus (local); starts the
    # Redis Streams consumer thread in distributed mode. Domain subscribers must
    # be registered before this call once they land (thumbnail PoC).
    platform.events.start()

    # Phase 1: critical pre-flight tasks.
    _run_alembic_migrations()
    await core_migrations.check_migrations()
    core_scheduler.start_scheduler()

    # Phase 2: best-effort background syncs and clean-up.
    core_logger.print_to_log_and_console("Refreshing Strava tokens on startup")
    _safe_run("refresh_strava_tokens", _refresh_strava_tokens)

    core_logger.print_to_log_and_console("Retrieving last day activities from Garmin Connect on startup")
    await _safe_run_async("retrieve_recent_garmin_activities", _retrieve_recent_garmin_activities)

    core_logger.print_to_log_and_console("Retrieving last day activities from Strava on startup")
    await _safe_run_async("retrieve_recent_strava_activities", _retrieve_recent_strava_activities)

    core_logger.print_to_log_and_console("Retrieving last day health stats from Garmin Connect on startup")
    await _safe_run_async(
        "retrieve_recent_garmin_health",
        _retrieve_recent_garmin_health,
    )

    core_logger.print_to_log_and_console("Purging expired tokens (password reset, sign-up, OAuth state, IdP link)")
    _safe_run("purge_expired_tokens", _purge_expired_tokens)

    core_logger.print_to_log_and_console("Scheduling missing activity map thumbnail generation")
    _safe_run("generate_missing_thumbnails", _generate_missing_thumbnails)

    core_logger.print_to_log_and_console("Initializing allowed tile domains for Content Security Policy")
    _init_allowed_tile_domains(fastapi_app)

    core_logger.print_to_log_and_console("Resolving TRUSTED_PROXIES hostnames")
    await _safe_run_async("resolve_trusted_proxy_hostnames", _resolve_trusted_proxy_hostnames)

    core_logger.print_to_log_and_console(f"Allowed trusted proxies: {core_config.settings.TRUSTED_PROXIES}")
    if core_config.settings._resolved_trusted_proxy_ips:
        core_logger.print_to_log_and_console(
            f"Resolved trusted proxy IPs: {sorted(core_config.settings._resolved_trusted_proxy_ips)}",
            "info",
        )


def shutdown_event(fastapi_app: FastAPI) -> None:
    """Stop the event bus and scheduler and release DB resources on shutdown."""
    core_logger.print_to_log_and_console("Backend shutdown event")

    # Stop the event bus consumer (no-op for the in-process bus; joins the Redis
    # Streams consumer thread in distributed mode). Guarded because startup may
    # have failed before the platform was attached.
    platform = getattr(fastapi_app.state, "platform", None)
    if platform is not None:
        platform.events.stop()

    core_scheduler.stop_scheduler()

    # Dispose the SQLAlchemy engine so all pooled
    # psycopg connections are closed deterministically.
    try:
        core_db_engine.dispose()
    except Exception as err:
        core_logger.print_to_log_and_console(
            f"Error disposing database engine on shutdown: {type(err).__name__}",
            "error",
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
    fastapi_app.mount(
        f"/{core_config.settings.ACTIVITY_THUMBNAILS_DIR}",
        StaticFiles(directory=core_config.settings.ACTIVITY_THUMBNAILS_DIR),
        name="activity_thumbnails",
    )

    # Router files
    fastapi_app.include_router(api_router)

    return fastapi_app


# Create the FastAPI application
app = create_app()
