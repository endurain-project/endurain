import logging

from fastapi import FastAPI
from routers import (
    router_session,
    router_users,
    router_activities,
    router_activity_streams,
    router_gear,
)
from constants import API_VERSION
from database import engine
import models

models.Base.metadata.create_all(bind=engine)

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
    "API_ENDPOINT",
]

# Router files
app.include_router(router_session.router)
app.include_router(router_users.router)
app.include_router(router_activities.router)
app.include_router(router_activity_streams.router)
app.include_router(router_gear.router)
