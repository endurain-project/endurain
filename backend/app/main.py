import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from alembic.config import Config
from alembic import command

import core.logger as core_logger
import core.config as core_config
import core.scheduler as core_scheduler
import core.tracing as core_tracing
import core.migrations as core_migrations

import garmin.activity_utils as garmin_activity_utils
import garmin.health_utils as garmin_health_utils

import strava.activity_utils as strava_activity_utils

from core.routes import router as api_router


def startup_event():
    core_logger.print_to_log_and_console(
        f"Backend startup event - {core_config.API_VERSION}"
    )

    # Run Alembic migrations to ensure the database is up to date
    alembic_cfg = Config("alembic.ini")
    # Disable the logger configuration in Alembic to avoid conflicts with FastAPI
    alembic_cfg.attributes["configure_logger"] = False
    command.upgrade(alembic_cfg, "head")

    # Migration check
    core_migrations.check_migrations()

    # Create a scheduler to run background jobs
    core_scheduler.start_scheduler()

    # Retrieve last day activities from Garmin Connect and Strava
    core_logger.print_to_log_and_console(
        "Retrieving last day activities from Garmin Connect and Strava on startup"
    )
    garmin_activity_utils.retrieve_garminconnect_users_activities_for_days(1)
    strava_activity_utils.retrieve_strava_users_activities_for_days(1)

    # Retrieve last day body composition from Garmin Connect
    core_logger.print_to_log_and_console(
        "Retrieving last day body composition from Garmin Connect on startup"
    )
    garmin_health_utils.retrieve_garminconnect_users_bc_for_days(1)


def shutdown_event():
    # Log the shutdown event
    core_logger.print_to_log_and_console("Backend shutdown event")

    # Shutdown the scheduler when the application is shutting down
    core_scheduler.stop_scheduler()


def create_app() -> FastAPI:
    # Define the FastAPI object
    app = FastAPI(
        docs_url="/docs",
        redoc_url="/redoc",
        title="Endurain",
        summary="Endurain API for the Endurain app",
        root_path="/api/v1",
        version=core_config.API_VERSION,
        license_info={
            "name": "GNU General Public License v3.0",
            "identifier": "GPL-3.0-or-later",
            "url": "https://spdx.org/licenses/GPL-3.0-or-later.html",
        },
    )

    # Add CORS middleware to allow requests from the frontend
    origins = [
        "http://localhost",
        "http://localhost:8080",
        "http://localhost:5173",
        os.environ.get("ENDURAIN_HOST"),
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Router files
    app.include_router(api_router)

    # Add a route to serve the user images
    app.mount("/user_images", StaticFiles(directory="user_images"), name="user_images")
    app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")

    return app


# Create the FastAPI application
app = create_app()

# Check for required environment variables
core_config.check_required_env_vars()

# Create logggers
core_logger.setup_main_logger()

# Setup tracing
core_tracing.setup_tracing(app)

# Register the startup event handler
app.add_event_handler("startup", startup_event)

# Register the shutdown event handler
app.add_event_handler("shutdown", shutdown_event)
