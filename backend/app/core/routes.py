from fastapi import APIRouter, Depends, Security

import core.router as core_router
import core.config as core_config
import session.router as session_router
import session.security as session_security
import users.user.router as users_router
import profile.router as profile_router
import users.user_default_gear.router as user_default_gear_router
import activities.activity.router as activities_router
import activities.activity_exercise_titles.router as activity_exercise_titles_router
import activities.activity_laps.router as activity_laps_router
import activities.activity_sets.router as activity_sets_router
import activities.activity_streams.router as activity_streams_router
import activities.activity_workout_steps.router as activity_workout_steps_router
import activity_summaries.router as activity_summaries_router
import gears.router as gears_router
import followers.router as followers_router
import strava.router as strava_router
import garmin.router as garmin_router
import health_data.router as health_data_router
import health_targets.router as health_targets_router
import server_settings.router as server_settings_router
import websocket.router as websocket_router

import users.user.public_router as users_public_router
import activities.activity.public_router as activities_public_router
import activities.activity_exercise_titles.public_router as activity_exercise_titles_public_router
import activities.activity_laps.public_router as activity_laps_public_router
import activities.activity_sets.public_router as activity_sets_public_router
import activities.activity_streams.public_router as activity_streams_public_router
import activities.activity_workout_steps.public_router as activity_workout_steps_public_router
import server_settings.public_router as server_settings_public_router

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
    user_default_gear_router.router,
    prefix=core_config.ROOT_PATH + "/profile/default_gear",
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
    activity_exercise_titles_router.router,
    prefix=core_config.ROOT_PATH + "/activities/exercise_titles",
    tags=["activity_exercise_titles"],
    dependencies=[Depends(session_security.validate_access_token)],
)
router.include_router(
    activity_laps_router.router,
    prefix=core_config.ROOT_PATH + "/activities/laps",
    tags=["activity_laps"],
    dependencies=[Depends(session_security.validate_access_token)],
)
router.include_router(
    activity_sets_router.router,
    prefix=core_config.ROOT_PATH + "/activities/sets",
    tags=["activity_sets"],
    dependencies=[Depends(session_security.validate_access_token)],
)
router.include_router(
    activity_streams_router.router,
    prefix=core_config.ROOT_PATH + "/activities/streams",
    tags=["activity_streams"],
    dependencies=[Depends(session_security.validate_access_token)],
)
router.include_router(
    activity_workout_steps_router.router,
    prefix=core_config.ROOT_PATH + "/activities/workout_steps",
    tags=["activity_workout_steps"],
    dependencies=[Depends(session_security.validate_access_token)],
)
router.include_router(
    activity_summaries_router.router,
    prefix=core_config.ROOT_PATH + "/summaries",
    tags=["summaries"],
    dependencies=[Depends(session_security.validate_access_token)],
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
    websocket_router.router,
    prefix=core_config.ROOT_PATH + "/ws",
    tags=["websocket"],
    #dependencies=[
    #   Depends(session_security.validate_access_token),
    #   Security(session_security.check_scopes, scopes=["profile"]),
    #],
)

# PUBLIC ROUTES
router.include_router(
    users_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/users",
    tags=["public_users"],
)
router.include_router(
    activities_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities",
    tags=["public_activities"],
)
router.include_router(
    activity_exercise_titles_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities/exercise_titles",
    tags=["public_activity_exercise_titles"],
)
router.include_router(
    activity_laps_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities/laps",
    tags=["public_activities_laps"],
)
router.include_router(
    activity_sets_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities/sets",
    tags=["public_activity_sets"],
)
router.include_router(
    activity_streams_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities/streams",
    tags=["public_activity_streams"],
)
router.include_router(
    activity_workout_steps_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities/workout_steps",
    tags=["public_activity_workout_steps"],
)
router.include_router(
    server_settings_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/server_settings",
    tags=["public_server_settings"],
)
router.include_router(
    core_router.router,
    tags=["core"],
)
