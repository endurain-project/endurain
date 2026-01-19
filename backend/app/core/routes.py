from fastapi import APIRouter, Depends, Security

# Alphabetized router imports
import activities.activity.router as activities_router
import activities.activity.public_router as activities_public_router
import activities.activity_exercise_titles.router as activity_exercise_titles_router
import activities.activity_exercise_titles.public_router as activity_exercise_titles_public_router
import activities.activity_laps.router as activity_laps_router
import activities.activity_laps.public_router as activity_laps_public_router
import activities.activity_media.router as activity_media_router
import activities.activity_sets.router as activity_sets_router
import activities.activity_sets.public_router as activity_sets_public_router
import activities.activity_streams.router as activity_streams_router
import activities.activity_streams.public_router as activity_streams_public_router
import activities.activity_summaries.router as activity_summaries_router
import activities.activity_workout_steps.router as activity_workout_steps_router
import activities.activity_workout_steps.public_router as activity_workout_steps_public_router
import auth.router as auth_router
import auth.identity_providers.router as identity_providers_router
import auth.identity_providers.public_router as identity_providers_public_router
import auth.security as auth_security
import core.config as core_config
import core.router as core_router
import followers.router as followers_router
import garmin.router as garmin_router
import gears.gear.router as gears_router
import gears.gear_components.router as gear_components_router
import health.health_sleep.router as health_sleep_router
import health.health_weight.router as health_weight_router
import health.health_steps.router as health_steps_router
import health.health_targets.router as health_targets_router
import notifications.router as notifications_router
import password_reset_tokens.router as password_reset_tokens_router
import profile.browser_redirect_router as profile_browser_redirect_router
import profile.router as profile_router
import server_settings.public_router as server_settings_public_router
import server_settings.router as server_settings_router
import users.users_session.router as users_session_router
import sign_up_tokens.router as sign_up_tokens_router
import strava.router as strava_router
import users.users.router as users_router
import users.users_goals.router as user_goals_router
import users.users_identity_providers.router as user_identity_providers_router
import users.users.public_router as users_public_router
import users.users_default_gear.router as user_default_gear_router
import websocket.router as websocket_router


router = APIRouter()

# Router files (alphabetical order)
router.include_router(
    activities_router.router,
    prefix=core_config.ROOT_PATH + "/activities",
    tags=["activities"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    activity_exercise_titles_router.router,
    prefix=core_config.ROOT_PATH + "/activities_exercise_titles",
    tags=["activity_exercise_titles"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    activity_laps_router.router,
    prefix=core_config.ROOT_PATH + "/activities_laps",
    tags=["activity_laps"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    activity_media_router.router,
    prefix=core_config.ROOT_PATH + "/activities_media",
    tags=["activity_media"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    activity_sets_router.router,
    prefix=core_config.ROOT_PATH + "/activities_sets",
    tags=["activity_sets"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    activity_streams_router.router,
    prefix=core_config.ROOT_PATH + "/activities_streams",
    tags=["activity_streams"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    activity_workout_steps_router.router,
    prefix=core_config.ROOT_PATH + "/activities_workout_steps",
    tags=["activity_workout_steps"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    activity_summaries_router.router,
    prefix=core_config.ROOT_PATH + "/activities_summaries",
    tags=["summaries"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    auth_router.router,
    prefix=core_config.ROOT_PATH + "/auth",
    tags=["auth"],
)
router.include_router(
    followers_router.router,
    prefix=core_config.ROOT_PATH + "/followers",
    tags=["followers"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    garmin_router.router,
    prefix=core_config.ROOT_PATH + "/garminconnect",
    tags=["garminconnect"],
    dependencies=[
        Depends(auth_security.validate_access_token),
        Security(auth_security.check_scopes, scopes=["profile"]),
    ],
)
router.include_router(
    gear_components_router.router,
    prefix=core_config.ROOT_PATH + "/gear_components",
    tags=["gear_components"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    gears_router.router,
    prefix=core_config.ROOT_PATH + "/gears",
    tags=["gears"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    health_sleep_router.router,
    prefix=core_config.ROOT_PATH + "/health/sleep",
    tags=["health_sleep"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    health_weight_router.router,
    prefix=core_config.ROOT_PATH + "/health/weight",
    tags=["health_weight"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    health_steps_router.router,
    prefix=core_config.ROOT_PATH + "/health/steps",
    tags=["health_steps"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    health_targets_router.router,
    prefix=core_config.ROOT_PATH + "/health_targets",
    tags=["health_targets"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    identity_providers_router.router,
    prefix=core_config.ROOT_PATH + "/idp",
    tags=["identity_providers"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    notifications_router.router,
    prefix=core_config.ROOT_PATH + "/notifications",
    tags=["notifications"],
    dependencies=[
        Depends(auth_security.validate_access_token),
        Security(auth_security.check_scopes, scopes=["profile"]),
    ],
)
router.include_router(
    password_reset_tokens_router.router,
    prefix=core_config.ROOT_PATH,
    tags=["password_reset_tokens"],
)
router.include_router(
    profile_browser_redirect_router.router,
    prefix=core_config.ROOT_PATH + "/profile",
    tags=["profile"],
    # No authentication required - endpoints validate via link_token parameter
)
router.include_router(
    profile_router.router,
    prefix=core_config.ROOT_PATH + "/profile",
    tags=["profile"],
    dependencies=[
        Depends(auth_security.validate_access_token),
        Security(auth_security.check_scopes, scopes=["profile"]),
    ],
)
router.include_router(
    server_settings_router.router,
    prefix=core_config.ROOT_PATH + "/server_settings",
    tags=["server_settings"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    users_session_router.router,
    prefix=core_config.ROOT_PATH + "/sessions",
    tags=["sessions"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    sign_up_tokens_router.router,
    prefix=core_config.ROOT_PATH,
    tags=["sign_up_tokens"],
)
router.include_router(
    strava_router.router,
    prefix=core_config.ROOT_PATH + "/strava",
    tags=["strava"],
)
router.include_router(
    user_default_gear_router.router,
    prefix=core_config.ROOT_PATH + "/profile/default_gear",
    tags=["profile"],
    dependencies=[
        Depends(auth_security.validate_access_token),
        Security(auth_security.check_scopes, scopes=["profile"]),
    ],
)
router.include_router(
    user_goals_router.router,
    prefix=core_config.ROOT_PATH + "/profile/goals",
    tags=["profile"],
    dependencies=[
        Depends(auth_security.validate_access_token),
        Security(auth_security.check_scopes, scopes=["profile"]),
    ],
)
router.include_router(
    user_identity_providers_router.router,
    prefix=core_config.ROOT_PATH,
    tags=["user_identity_providers"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    users_router.router,
    prefix=core_config.ROOT_PATH + "/users",
    tags=["users"],
    dependencies=[Depends(auth_security.validate_access_token)],
)
router.include_router(
    websocket_router.router,
    prefix=core_config.ROOT_PATH + "/ws",
    tags=["websocket"],
)

# PUBLIC ROUTES (alphabetical order)
router.include_router(
    activities_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities",
    tags=["public_activities"],
)
router.include_router(
    activity_exercise_titles_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities_exercise_titles",
    tags=["public_activity_exercise_titles"],
)
router.include_router(
    activity_laps_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities_laps",
    tags=["public_activities_laps"],
)
router.include_router(
    activity_sets_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities_sets",
    tags=["public_activity_sets"],
)
router.include_router(
    activity_streams_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities_streams",
    tags=["public_activity_streams"],
)
router.include_router(
    activity_workout_steps_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities_workout_steps",
    tags=["public_activity_workout_steps"],
)
router.include_router(
    identity_providers_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/idp",
    tags=["identity_providers_public"],
)
router.include_router(
    server_settings_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/server_settings",
    tags=["public_server_settings"],
)
router.include_router(
    users_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/users",
    tags=["public_users"],
)
router.include_router(
    core_router.router,
    tags=["core"],
)
