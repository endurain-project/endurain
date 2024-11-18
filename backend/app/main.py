import logging
import os

from fastapi import FastAPI, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from alembic.config import Config
from alembic import command

from apscheduler.schedulers.background import BackgroundScheduler

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

import strava.utils as strava_utils
import strava.activity_utils as strava_activity_utils

import garmin.activity_utils as garmin_activity_utils

import migrations.utils as migrations_utils

from config import API_VERSION
from database import SessionLocal
from routes import router as api_router


def startup_event():
    print("Backend startup event")
    logger.info("Backend startup event")

    # Run Alembic migrations to ensure the database is up to date
    alembic_cfg = Config("alembic.ini")
    # Disable the logger configuration in Alembic to avoid conflicts with FastAPI
    alembic_cfg.attributes["configure_logger"] = False
    command.upgrade(alembic_cfg, "head")

    # Migration check
    check_migrations()

    # Create a scheduler to run background jobs
    scheduler.start()

    # Add scheduler jobs to refresh Strava tokens and retrieve last day activities
    logger.info("Added scheduler job to refresh Strava user tokens every 60 minutes")
    scheduler.add_job(refresh_strava_tokens_job, "interval", minutes=60)
    logger.info(
        "Added scheduler job to retrieve last day Strava users activities every 60 minutes"
    )
    scheduler.add_job(
        retrieve_strava_user_activities_for_last_day, "interval", minutes=60
    )

    # Add scheduler jobs to retrieve last day activities from Garmin Connect
    logger.info(
        "Added scheduler job to retrieve last day Garmin Connect users activities every 60 minutes"
    )
    scheduler.add_job(
        retrieve_garminconnect_user_activities_for_last_day, "interval", minutes=60
    )


def shutdown_event():
    print("Backend shutdown event")
    logger.info("Backend shutdown event")

    # Shutdown the scheduler when the application is shutting down
    scheduler.shutdown()


def check_migrations():
    logger.info("Checking for migrations not executed")
    # Create a new database session
    db = SessionLocal()
    try:
        # Check migrations not executed
        migrations_utils.check_migrations_not_executed(db)
    finally:
        # Ensure the session is closed after use
        db.close()
        logger.info("Migration check completed")


def refresh_strava_tokens_job():
    # Create a new database session
    db = SessionLocal()
    try:
        # Refresh Strava tokens
        strava_utils.refresh_strava_tokens(db)
    finally:
        # Ensure the session is closed after use
        db.close()


def retrieve_strava_user_activities_for_last_day():
    # Get last day users Strava activities
    strava_activity_utils.retrieve_strava_users_activities_for_days(1)


def retrieve_garminconnect_user_activities_for_last_day():
    # Get last day users Garmin Connect activities
    garmin_activity_utils.retrieve_garminconnect_users_activities_for_days(1)


# Create loggger
logger = logging.getLogger("myLogger")
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler("logs/app.log")
file_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)

# Check for required environment variables
required_env_vars = [
    "DB_HOST",
    "DB_PORT",
    "DB_USER",
    "DB_PASSWORD",
    "DB_DATABASE",
    "SECRET_KEY",
    "ALGORITHM",
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "REFRESH_TOKEN_EXPIRE_DAYS",
    "STRAVA_CLIENT_ID",
    "STRAVA_CLIENT_SECRET",
    "STRAVA_AUTH_CODE",
    "JAEGER_ENABLED",
    "JAEGER_PROTOCOL",
    "JAEGER_HOST",
    "JAGGER_PORT",
    "FRONTEND_PROTOCOL",
    "FRONTEND_HOST",
    "GEOCODES_MAPS_API",
]

for var in required_env_vars:
    if var not in os.environ:
        logger.error(f"Missing required environment variable: {var}", exc_info=True)
        raise EnvironmentError(f"Missing required environment variable: {var}")

# Create a background scheduler instance
scheduler = BackgroundScheduler()

# Define the FastAPI object
app = FastAPI(
    docs_url="/docs",
    redoc_url="/redoc",
    title="Endurain",
    summary="Endurain API for the Endurain app",
    root_path="/api/v1",
    version=API_VERSION,
    license_info={
        "name": "GNU General Public License v3.0",
        "identifier": "GPL-3.0-or-later",
        "url": "https://spdx.org/licenses/GPL-3.0-or-later.html",
    },
)

# Add a route to serve the user images
app.mount("/user_images", StaticFiles(directory="user_images"), name="user_images")

# Add CORS middleware to allow requests from the frontend
origins = [
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:5173",
    os.environ.get("FRONTEND_PROTOCOL") + "://" + os.environ.get("FRONTEND_HOST"),
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

# Check if Jaeger tracing is enabled using the 'JAEGER_ENABLED' environment variable
if os.environ.get("JAEGER_ENABLED") == "true":
    # Configure OpenTelemetry with a specified service name
    trace.set_tracer_provider(
        TracerProvider(resource=Resource.create({"service.name": "backend_api"}))
    )
    trace.get_tracer_provider().add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=os.environ.get("JAEGER_PROTOCOL")
                + "://"
                + os.environ.get("JAEGER_HOST")
                + ":"
                + os.environ.get("JAGGER_PORT")
            )
        )
    )


# Instrument FastAPI app
FastAPIInstrumentor.instrument_app(app)

# Register the startup event handler
app.add_event_handler("startup", startup_event)

# Register the shutdown event handler
app.add_event_handler("shutdown", shutdown_event)

@app.get(
    "/about",
)
async def about(
):
    # Return the gear
    return {
        "name": "Endurain API",
        "version": API_VERSION,
        "license": {
            "name": "GNU General Public License v3.0",
            "identifier": "GPL-3.0-or-later",
            "url": "https://spdx.org/licenses/GPL-3.0-or-later.html",
        },
    }