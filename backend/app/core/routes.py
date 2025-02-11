from fastapi import APIRouter, Depends, Security

import core.router as core_router
import core.config as core_config
import session.router as session_router
import session.security as session_security
import users.router as users_router
import profile.router as profile_router
import activities.router as activities_router
import activities.public_router as activities_public_router
import activity_streams.router as activity_streams_router
import activity_streams.public_router as activity_streams_public_router
import gears.router as gears_router
import followers.router as followers_router
import strava.router as strava_router
import garmin.router as garmin_router
import health_data.router as health_data_router
import health_targets.router as health_targets_router
import server_settings.router as server_settings_router
import server_settings.public_router as server_settings_public_router
import websocket.router as websocket_router


router = APIRouter()


# Router files
router.include_router(
    session_router.router,
    prefix=core_config.ROOT_PATH,
    tags=["sessions"],
)
router.include_router(
    users_router.router,
    prefix=core_config.ROOT_PATH + "/users",
    tags=["users"],
    dependencies=[Depends(session_security.validate_access_token)],
)
router.include_router(
    profile_router.router,
    prefix=core_config.ROOT_PATH + "/profile",
    tags=["profile"],
    dependencies=[
        Depends(session_security.validate_access_token),
        Security(session_security.check_scopes, scopes=["profile"]),
    ],
)
router.include_router(
    activities_router.router,
    prefix=core_config.ROOT_PATH + "/activities",
    tags=["activities"],
    dependencies=[Depends(session_security.validate_access_token)],
)
router.include_router(
    activities_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities",
    tags=["public_activities"],
)
router.include_router(
    activity_streams_router.router,
    prefix=core_config.ROOT_PATH + "/activities/streams",
    tags=["activity_streams"],
    dependencies=[Depends(session_security.validate_access_token)],
)
router.include_router(
    activity_streams_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities/streams",
    tags=["public_activity_streams"],
)
router.include_router(
    gears_router.router,
    prefix=core_config.ROOT_PATH + "/gears",
    tags=["gears"],
    dependencies=[Depends(session_security.validate_access_token)],
)
router.include_router(
    followers_router.router,
    prefix=core_config.ROOT_PATH + "/followers",
    tags=["followers"],
    dependencies=[Depends(session_security.validate_access_token)],
)
router.include_router(
    strava_router.router,
    prefix=core_config.ROOT_PATH + "/strava",
    tags=["strava"],
)
router.include_router(
    garmin_router.router,
    prefix=core_config.ROOT_PATH + "/garminconnect",
    tags=["garminconnect"],
    dependencies=[
        Depends(session_security.validate_access_token),
        Security(session_security.check_scopes, scopes=["profile"]),
    ],
)
router.include_router(
    health_data_router.router,
    prefix=core_config.ROOT_PATH + "/health",
    tags=["health"],
    dependencies=[Depends(session_security.validate_access_token)],
)
router.include_router(
    health_targets_router.router,
    prefix=core_config.ROOT_PATH + "/health_targets",
    tags=["health_targets"],
    dependencies=[Depends(session_security.validate_access_token)],
)
router.include_router(
    server_settings_router.router,
    prefix=core_config.ROOT_PATH + "/server_settings",
    tags=["server_settings"],
    dependencies=[Depends(session_security.validate_access_token)],
)
router.include_router(
    server_settings_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/server_settings",
    tags=["public_server_settings"],
)
router.include_router(
    websocket_router.router,
    prefix=core_config.ROOT_PATH + "/ws",
    tags=["websocket"],
    # dependencies=[
    #    Depends(session_security.validate_access_token),
    #    Security(session_security.check_scopes, scopes=["profile"]),
    # ],
)
router.include_router(
    core_router.router,
    tags=["core"],
)
