"""
Main Application File for Backend API

This file contains the configuration and setup for a FastAPI-based backend API. It includes routing for various controllers, background jobs scheduled using the Advanced Python Scheduler (APScheduler), OpenTelemetry for distributed tracing, and event handlers for startup and shutdown processes.

Modules and Libraries:
- FastAPI: Web framework for building APIs with Python.
- APScheduler: Library for scheduling background jobs.
- OpenTelemetry: A set of APIs, libraries, agents, instrumentation, and instrumentation bindings for observability in software systems.
- SQLAlchemy: SQL toolkit and Object-Relational Mapping (ORM) for Python.
- Other custom modules for controllers, database management, and dependencies.

Key Features:
- OpenTelemetry Integration: Configures OpenTelemetry for distributed tracing, including Jaeger exporter if specified in the environment.
- Background Jobs: Uses APScheduler to schedule periodic tasks, such as removing expired tokens, refreshing Strava tokens, and fetching Strava activities.
- FastAPI Instrumentation: Instruments the FastAPI app for automatic tracing and observability.
- Database Initialization: Initializes the database and creates tables during startup.
- Event Handlers: Registers startup and shutdown event handlers to execute tasks at the beginning and end of the application lifecycle.

Environment Variables:
- JAEGER_ENABLED: Flag to enable or disable Jaeger tracing.
- JAEGER_PROTOCOL, JAEGER_HOST, JAGGER_PORT: Jaeger exporter configuration.

Routes:
- Session, User, Gear, Activity, Follower, and Strava controllers are included as routers.

Event Handlers:
- "startup": Triggers the creation of database tables during application startup.
- "shutdown": Triggers the shutdown of the background scheduler when the application is shutting down.

Note: Ensure that required dependencies are installed and environment variables are properly configured before running the application.
"""
# Import FastAPI framework for building APIs
from fastapi import FastAPI

# Import Advanced Python Scheduler for background jobs
from apscheduler.schedulers.background import BackgroundScheduler

# Import controllers for different routes
from controllers import (
    sessionController,
    userController,
    gearController,
    activityController,
    followerController,
    stravaController,
)

# Import datetime for handling date and time
from datetime import datetime, timedelta

# Import OpenTelemetry for distributed tracing
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Import FastAPI instrumentation for automatic tracing
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# Import OS module for handling environment variables
import os

import logging

# Import database-related functions and dependencies
from db.db import create_database_tables
from dependencies import get_db_session, configure_logger

# Define the FastAPI object
app = FastAPI()

# Create loggger
#logger = configure_logger()
logger = logging.getLogger("myLogger")
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler("app.log")
file_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)

# Check for required environment variables
required_env_vars = ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_DATABASE", "SECRET_KEY", "ALGORITHM", "ACCESS_TOKEN_EXPIRE_MINUTES", "STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_AUTH_CODE", "JAEGER_ENABLED", "JAEGER_PROTOCOL", "JAEGER_HOST", "JAGGER_PORT", "STRAVA_DAYS_ACTIVITIES_ONLINK", "API_ENDPOINT"]

for var in required_env_vars:
    if var not in os.environ:
        logger.error(f"Missing required environment variable: {var}", exc_info=True)
        raise EnvironmentError(f"Missing required environment variable: {var}")


def startup_event():
    """
    Event handler for application startup.

    This function is responsible for creating the database and tables if they don't exist during the startup of the FastAPI application.

    Raises:
    - None.

    Returns:
    - None.
    """
    logger.info("Backend startup event")
    # Create the database and tables if they don't exist
    create_database_tables()
    logger.info("Will check if there is expired tokens to remove")
    sessionController.remove_expired_tokens(db_session=get_db_session())


def shutdown_event():
    """
    Event handler for application shutdown.

    This function is responsible for shutting down the background scheduler when the FastAPI application is shutting down.

    Raises:
    - None.

    Returns:
    - None.
    """
    logger.info("Backend shutdown event")
    scheduler.shutdown()


def remove_expired_tokens_job():
    """
    Background job to remove expired user authentication tokens.

    This job is scheduled to run at regular intervals, and its purpose is to identify and remove authentication tokens
    that have expired. It calls the `remove_expired_tokens` function from the sessionController module.

    Parameters:
    - None.

    Raises:
    - Exception: If an unexpected error occurs during the token removal process.

    Returns:
    - None.
    """
    try:
        sessionController.remove_expired_tokens(db_session=get_db_session())
    except Exception as err:
        logger.error(f"Error in remove_expired_tokens_job: {err}", exc_info=True)


def refresh_strava_token_job():
    """
    Background job to refresh the Strava authentication token.

    This job is scheduled to run at regular intervals, and its purpose is to refresh the authentication token
    used for interacting with the Strava API. It calls the `refresh_strava_token` function from the stravaController module.

    Parameters:
    - None.

    Raises:
    - Exception: If an unexpected error occurs during the token refresh process.

    Returns:
    - None.
    """
    try:
        stravaController.refresh_strava_token(db_session=get_db_session())
    except Exception as err:
        logger.error(f"Error in refresh_strava_token_job: {err}", exc_info=True)


def get_strava_activities_job():
    """
    Background job to fetch Strava activities.

    This job is scheduled to run at regular intervals, and its purpose is to retrieve Strava activities
    from the past 24 hours. It calls the `get_strava_activities` function from the stravaController module.

    Parameters:
    - None.

    Raises:
    - Exception: If an unexpected error occurs during the Strava activities retrieval process.

    Returns:
    - None.
    """
    try:
        stravaController.get_strava_activities(
            (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            db_session=get_db_session(),
        )
    except Exception as err:
        logger.error(f"Error in get_strava_activities_job: {err}", exc_info=True)


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

# Router files
app.include_router(sessionController.router)
app.include_router(userController.router)
app.include_router(gearController.router)
app.include_router(activityController.router)
app.include_router(followerController.router)
app.include_router(stravaController.router)

# Create a background scheduler instance
scheduler = BackgroundScheduler()
scheduler.start()


# Job to remove expired tokens every 5 minutes
scheduler.add_job(remove_expired_tokens_job, "interval", minutes=5)

# Job to refresh the Strava token every 30 minutes
scheduler.add_job(refresh_strava_token_job, "interval", minutes=30)

# Job to get Strava activities every hour
scheduler.add_job(get_strava_activities_job, "interval", minutes=60)

# Register the startup event handler
app.add_event_handler("startup", startup_event)

# Register the shutdown event handler
app.add_event_handler("shutdown", shutdown_event)
