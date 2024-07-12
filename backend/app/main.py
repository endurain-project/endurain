import logging
import os

from fastapi import FastAPI, Request, Depends
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

# from session import router as session_router
# from users import router as users_router
# from activities import router as activities_router
# from activity_streams import router as activity_streams_router
# from gears import router as gears_router
# from followers import router as followers_router

import session.router as session_router
import session.security as session_security
import users.router as users_router
import activities.router as activities_router
import activity_streams.router as activity_streams_router
import gears.router as gears_router
import followers.router as followers_router

from routers import (
    router_strava,
)

from config import API_VERSION
from database import SessionLocal
from processors import strava_processor, strava_activity_processor


def startup_event():
    print("Backend startup event")
    logger.info("Backend startup event")

    # Run Alembic migrations to ensure the database is up to date
    alembic_cfg = Config("alembic.ini")
    # Disable the logger configuration in Alembic to avoid conflicts with FastAPI
    alembic_cfg.attributes["configure_logger"] = False
    command.upgrade(alembic_cfg, "head")

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


def shutdown_event():
    print("Backend shutdown event")
    logger.info("Backend shutdown event")

    # Shutdown the scheduler when the application is shutting down
    scheduler.shutdown()


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
    "REFRESH_TOKEN_EXPIRE_DAYS",
    "STRAVA_CLIENT_ID",
    "STRAVA_CLIENT_SECRET",
    "STRAVA_AUTH_CODE",
    "JAEGER_ENABLED",
    "JAEGER_PROTOCOL",
    "JAEGER_HOST",
    "JAGGER_PORT",
    "STRAVA_DAYS_ACTIVITIES_ONLINK",
    "FRONTEND_PROTOCOL",
    "FRONTEND_HOST",
    "FRONTEND_PORT",
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

# Add a route to serve the user images
app.mount("/user_images", StaticFiles(directory="user_images"), name="user_images")

# Add CORS middleware to allow requests from the frontend
origins = [
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:5173",
    os.environ.get("FRONTEND_PROTOCOL")
    + "://"
    + os.environ.get("FRONTEND_HOST")
    + ":"
    + os.environ.get("FRONTEND_PORT"),
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router files
app.include_router(
    session_router.router,
    tags=["session"],
)
app.include_router(
    users_router.router,
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(session_security.validate_access_token)],
)
app.include_router(
    activities_router.router,
    prefix="/activities",
    tags=["activities"],
    dependencies=[Depends(session_security.validate_access_token)],
)
app.include_router(
    activity_streams_router.router,
    prefix="/activities/streams",
    tags=["activity_streams"],
    dependencies=[Depends(session_security.validate_access_token)],
)
app.include_router(
    gears_router.router,
    prefix="/gears",
    tags=["gears"],
    dependencies=[Depends(session_security.validate_access_token)],
)
app.include_router(
    followers_router.router,
    prefix="/followers",
    tags=["followers"],
    dependencies=[Depends(session_security.validate_access_token)],
)
app.include_router(router_strava.router, tags=["strava"])

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
