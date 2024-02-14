import logging
import os

from fastapi import FastAPI

from alembic.config import Config
from alembic import command

from apscheduler.schedulers.background import BackgroundScheduler

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from routers import (
    router_session,
    router_users,
    router_activities,
    router_activity_streams,
    router_gear,
    router_followers,
    router_strava,
)
from constants import API_VERSION
from schemas import schema_access_tokens
from database import SessionLocal
from processors import strava_processor, strava_activity_processor


def startup_event():
    print("Backend startup event")
    logger.info("Backend startup event")

    # Run Alembic migrations to ensure the database is up to date
    alembic_cfg = Config("alembic.ini")
    # Disable the logger configuration in Alembic to avoid conflicts with FastAPI
    alembic_cfg.attributes['configure_logger'] = False
    command.upgrade(alembic_cfg, "head")

    # Create a scheduler to run background jobs
    scheduler.start()

    # Job to remove expired tokens every 5 minutes
    logger.info("Added scheduler job to remove expired tokens every 5 minutes")
    scheduler.add_job(remove_expired_tokens_job, "interval", minutes=5)
    logger.info("Added scheduler job to refresh Strava user tokens every 60 minutes")
    scheduler.add_job(refresh_strava_tokens_job, "interval", minutes=60)
    logger.info(
        "Added scheduler job to retrieve last day Strava users activities every 60 minutes"
    )
    scheduler.add_job(
        retrieve_strava_user_activities_for_last_day, "interval", minutes=60
    )


def shutdown_event():
    print("Backend shutdown event")
    logger.info("Backend shutdown event")

    # Shutdown the scheduler when the application is shutting down
    scheduler.shutdown()


def remove_expired_tokens_job():
    # Create a new database session
    db = SessionLocal()
    try:
        # Remove expired tokens from the database
        schema_access_tokens.remove_expired_tokens(db=db)
    finally:
        # Ensure the session is closed after use
        db.close()


def refresh_strava_tokens_job():
    # Create a new database session
    db = SessionLocal()
    try:
        # Refresh Strava tokens
        strava_processor.refresh_strava_tokens(db=db)
    finally:
        # Ensure the session is closed after use
        db.close()


def retrieve_strava_user_activities_for_last_day():
    # Get last day users Strava activities
    strava_activity_processor.retrieve_strava_users_activities_for_days(1)


# Create loggger
logger = logging.getLogger("myLogger")
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler("app.log")
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
    "STRAVA_CLIENT_ID",
    "STRAVA_CLIENT_SECRET",
    "STRAVA_AUTH_CODE",
    "JAEGER_ENABLED",
    "JAEGER_PROTOCOL",
    "JAEGER_HOST",
    "JAGGER_PORT",
    "STRAVA_DAYS_ACTIVITIES_ONLINK",
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
    version=API_VERSION,
    license_info={
        "name": "GNU General Public License v3.0",
        "identifier": "GPL-3.0-or-later",
        "url": "https://spdx.org/licenses/GPL-3.0-or-later.html",
    },
)

# Router files
app.include_router(router_session.router)
app.include_router(router_users.router)
app.include_router(router_activities.router)
app.include_router(router_activity_streams.router)
app.include_router(router_gear.router)
app.include_router(router_followers.router)
app.include_router(router_strava.router)

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
