import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from alembic.config import Config
from alembic import command

import core.logger as core_logger
import core.config as core_config
import core.scheduler as core_scheduler
import core.tracing as core_tracing
import core.middleware as core_middleware
import core.migrations as core_migrations
import core.rate_limit as core_rate_limit

import garmin.activity_utils as garmin_activity_utils
import garmin.health_utils as garmin_health_utils

import strava.activity_utils as strava_activity_utils
import strava.utils as strava_utils

import password_reset_tokens.utils as password_reset_tokens_utils

import sign_up_tokens.utils as sign_up_tokens_utils

import auth.oauth_state.utils as oauth_state_utils
import auth.idp_link_tokens.utils as idp_link_token_utils

import server_settings.utils as server_settings_utils
import server_settings.schema as server_settings_schema

from core.routes import router as api_router
from core.database import SessionLocal


async def startup_event():
    core_logger.print_to_log_and_console(
        f"Backend startup event - {core_config.API_VERSION}"
    )

    # Run Alembic migrations to ensure the database is up to date
    alembic_cfg = Config("alembic.ini")
    # Disable the logger configuration in Alembic to avoid conflicts with FastAPI
    alembic_cfg.attributes["configure_logger"] = False
    command.upgrade(alembic_cfg, "head")

    # Migration check
    await core_migrations.check_migrations()

    # Create a scheduler to run background jobs
    core_scheduler.start_scheduler()

    # Retrieve last day activities from Garmin Connect and Strava
    core_logger.print_to_log_and_console(
        "Refreshing Strava tokens on startup on startup"
    )
    strava_utils.refresh_strava_tokens(True)

    # Retrieve last day activities from Garmin Connect and Strava
    core_logger.print_to_log_and_console(
        "Retrieving last day activities from Garmin Connect and Strava on startup"
    )
    await garmin_activity_utils.retrieve_garminconnect_users_activities_for_days(1)
    await strava_activity_utils.retrieve_strava_users_activities_for_days(1, True)

    # Retrieve last day health stats from Garmin Connect
    core_logger.print_to_log_and_console(
        "Retrieving last day health stats from Garmin Connect on startup"
    )
    garmin_health_utils.retrieve_garminconnect_users_health_for_days(1)

    # Delete invalid password reset tokens
    core_logger.print_to_log_and_console(
        "Deleting invalid password reset tokens from the database"
    )
    password_reset_tokens_utils.delete_invalid_tokens_from_db()

    # Delete invalid sign-up tokens
    core_logger.print_to_log_and_console(
        "Deleting invalid sign-up tokens from the database"
    )
    sign_up_tokens_utils.delete_invalid_tokens_from_db()

    # Delete expired OAuth states
    core_logger.print_to_log_and_console(
        "Deleting expired OAuth states from the database"
    )
    oauth_state_utils.delete_expired_oauth_states_from_db()

    # Delete expired IdP link tokens
    core_logger.print_to_log_and_console(
        "Deleting expired IdP link tokens from the database"
    )
    idp_link_token_utils.delete_idp_link_expired_tokens_from_db()

    # Initialize allowed tile domains for CSP
    core_logger.print_to_log_and_console(
        "Initializing allowed tile domains for Content Security Policy"
    )
    with SessionLocal() as db:
        try:
            app.state.allowed_tile_domains = (
                server_settings_utils.get_allowed_tile_domains(db)
            )
            core_logger.print_to_log_and_console(
                f"Allowed tile domains: {app.state.allowed_tile_domains}"
            )
        except Exception as err:
            core_logger.print_to_log(
                f"Error initializing tile domains, using defaults: {err}",
                "error",
                exc=err,
            )
            # Fallback to built-in providers
            app.state.allowed_tile_domains = (
                server_settings_schema.DEFAULT_ALLOWED_TILE_DOMAINS.copy()
            )


def shutdown_event():
    # Log the shutdown event
    core_logger.print_to_log_and_console("Backend shutdown event")

    # Shutdown the scheduler when the application is shutting down
    core_scheduler.stop_scheduler()


def create_app() -> FastAPI:
    # Define the FastAPI object
    fastapi_app = FastAPI(
        docs_url=core_config.ROOT_PATH + "/docs",
        redoc_url=core_config.ROOT_PATH + "/redoc",
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
        secret_key=core_config.read_secret("SECRET_KEY"),
        session_cookie="endurain_session",
        max_age=3600,  # 1 hour session timeout
        same_site="lax",
        https_only=(
            core_config.ENVIRONMENT == "production" or core_config.ENVIRONMENT == "demo"
        ),
    )

    # Add CORS middleware to allow requests from the frontend
    origins = [
        "http://localhost:8080",
        "http://localhost:5173",
        core_config.ENDURAIN_HOST,
    ]

    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=(
            origins
            if core_config.ENVIRONMENT == "development"
            else core_config.ENDURAIN_HOST
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add security headers middleware (before CSRF for proper header ordering)
    fastapi_app.add_middleware(core_middleware.SecurityHeadersMiddleware)

    # Add CSRF protection middleware
    fastapi_app.add_middleware(core_middleware.CSRFMiddleware)

    # Add rate limiting
    fastapi_app.state.limiter = core_rate_limit.limiter
    fastapi_app.add_exception_handler(
        core_rate_limit.RateLimitExceeded, core_rate_limit.rate_limit_exceeded_handler
    )

    # Router files
    fastapi_app.include_router(api_router)

    # Add a route to serve the user images
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
        f"/{core_config.ACTIVITY_MEDIA_DIR}",
        StaticFiles(directory=core_config.ACTIVITY_MEDIA_DIR),
        name="activity_media",
    )

    return fastapi_app


# Silence stravalib token warnings
os.environ["SILENCE_TOKEN_WARNINGS"] = "TRUE"

# Check for required environment variables
core_config.check_required_env_vars()

# Check for required directories
core_config.check_required_dirs()

# Create the FastAPI application
app = create_app()

# Create logggers
core_logger.setup_main_logger()

# Setup tracing
core_tracing.setup_tracing(app)

# Register the startup event handler
app.add_event_handler("startup", startup_event)

# Register the shutdown event handler
app.add_event_handler("shutdown", shutdown_event)
