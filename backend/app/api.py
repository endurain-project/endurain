"""Aggregate application routers under the API root."""

from fastapi import APIRouter, Depends, Security

import core.config as core_config
import core.router as core_router
import modules.activities.activity.dependencies as activities_dependencies
import modules.activities.activity.public_router as activities_public_router

# Alphabetized router imports
import modules.activities.activity.router as activities_router
import modules.activities.activity_ingestion.router as activity_ingestion_router
import modules.activities.activity_laps.public_router as activity_laps_public_router
import modules.activities.activity_laps.router as activity_laps_router
import modules.activities.activity_media.router as activity_media_router
import modules.activities.activity_sets.public_router as activity_sets_public_router
import modules.activities.activity_sets.router as activity_sets_router
import modules.activities.activity_streams.router as activity_streams_router
import modules.activities.activity_summaries.router as activity_summaries_router
import modules.activities.activity_thumbnail.router as activity_thumbnail_router
import modules.auth.api_keys.router as auth_api_keys_router
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_providers.router as identity_providers_router
import modules.auth.password_reset_tokens.router as password_reset_tokens_router
import modules.auth.router as auth_router
import modules.auth.sessions.router as auth_sessions_router
import modules.auth.sign_up_tokens.router as sign_up_tokens_router
import modules.followers.router as followers_router
import modules.garmin.router as garmin_router
import modules.gears.gear.router as gears_router
import modules.gears.gear_components.router as gear_components_router
import modules.health.health_fasting.router as health_fasting_router
import modules.health.health_poop.router as health_poop_router
import modules.health.health_sleep.router as health_sleep_router
import modules.health.health_steps.router as health_steps_router
import modules.health.health_targets.router as health_targets_router
import modules.health.health_water.router as health_water_router
import modules.health.health_weight.router as health_weight_router
import modules.health.router as health_router
import modules.notifications.router as notifications_router
import modules.server_settings.event_log_router as event_log_router
import modules.server_settings.jobs_router as jobs_router
import modules.server_settings.public_router as server_settings_public_router
import modules.server_settings.router as server_settings_router
import modules.strava.router as strava_router
import modules.users.users.public_router as users_public_router
import modules.users.users.router as users_router
import modules.users.users_default_gear.router as user_default_gear_router
import modules.users.users_goals.router as user_goals_router
import modules.users.users_profile.browser_redirect_router as profile_browser_redirect_router
import modules.users.users_profile.router as profile_router
import modules.websocket.router as websocket_router
from modules.activities.activity_exercise_titles import (
    public_router as activity_exercise_titles_public_router,
)
from modules.activities.activity_exercise_titles import (
    router as activity_exercise_titles_router,
)
from modules.activities.activity_streams import (
    public_router as activity_streams_public_router,
)
from modules.activities.activity_workout_steps import (
    public_router as activity_workout_steps_public_router,
)
from modules.activities.activity_workout_steps import (
    router as activity_workout_steps_router,
)
from modules.auth.identity_providers import (
    public_router as identity_providers_public_router,
)

router = APIRouter()

# Router files (alphabetical order)
# NOTE: the activity_ingestion routers are mounted BEFORE the activities core router on
# purpose. They expose literal ``/activities`` paths (``/refresh``, ``/upload``,
# ``/bulk-import``) that must be matched before the core router's dynamic
# ``/activities/{activity_id}`` catch-all — Starlette resolves routes in registration
# order, so a later literal would be shadowed by the earlier ``/{activity_id}``.
router.include_router(
    activity_ingestion_router.router,
    prefix=core_config.ROOT_PATH + "/activities",
    tags=["activities"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    activity_ingestion_router.api_upload_router,
    prefix=core_config.ROOT_PATH + "/activities",
    tags=["activities"],
    dependencies=[Depends(auth_dependencies.validate_access_token_or_api_key)],
)
# The thumbnail route is intentionally UNAUTHENTICATED: its access control is the
# signed ``?t=`` token in the URL (see activity_thumbnail.signing), which lets it
# be used in an ``<img src>`` tag. Mounted before the core activities router so
# its ``/{activity_id}/thumbnail`` path is matched ahead of the dynamic routes.
router.include_router(
    activity_thumbnail_router.router,
    prefix=core_config.ROOT_PATH + "/activities",
    tags=["activities"],
)
router.include_router(
    activities_router.router,
    prefix=core_config.ROOT_PATH + "/activities",
    tags=["activities"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    activity_exercise_titles_router.router,
    prefix=core_config.ROOT_PATH + "/activities_exercise_titles",
    tags=["activity_exercise_titles"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    activity_laps_router.router,
    prefix=core_config.ROOT_PATH + "/activities/{activity_id}",
    tags=["activity_laps"],
    dependencies=[
        Depends(auth_dependencies.validate_access_token),
        Depends(activities_dependencies.validate_activity_id),
    ],
)
router.include_router(
    activity_media_router.router,
    prefix=core_config.ROOT_PATH + "/activities/{activity_id}",
    tags=["activity_media"],
    dependencies=[
        Depends(auth_dependencies.validate_access_token),
        Depends(activities_dependencies.validate_activity_id),
    ],
)
router.include_router(
    activity_sets_router.router,
    prefix=core_config.ROOT_PATH + "/activities/{activity_id}",
    tags=["activity_sets"],
    dependencies=[
        Depends(auth_dependencies.validate_access_token),
        Depends(activities_dependencies.validate_activity_id),
    ],
)
router.include_router(
    activity_streams_router.router,
    prefix=core_config.ROOT_PATH + "/activities/{activity_id}",
    tags=["activity_streams"],
    dependencies=[
        Depends(auth_dependencies.validate_access_token),
        Depends(activities_dependencies.validate_activity_id),
    ],
)
router.include_router(
    activity_workout_steps_router.router,
    prefix=core_config.ROOT_PATH + "/activities/{activity_id}",
    tags=["activity_workout_steps"],
    dependencies=[
        Depends(auth_dependencies.validate_access_token),
        Depends(activities_dependencies.validate_activity_id),
    ],
)
router.include_router(
    activity_summaries_router.router,
    prefix=core_config.ROOT_PATH + "/activities_summaries",
    tags=["summaries"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    auth_router.router,
    prefix=core_config.ROOT_PATH + "/auth",
    tags=["auth"],
)
router.include_router(
    event_log_router.router,
    prefix=core_config.ROOT_PATH + "/event_log",
    tags=["event_log"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    jobs_router.router,
    prefix=core_config.ROOT_PATH + "/jobs",
    tags=["jobs"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    followers_router.router,
    prefix=core_config.ROOT_PATH + "/followers",
    tags=["followers"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    garmin_router.router,
    prefix=core_config.ROOT_PATH + "/garminconnect",
    tags=["garminconnect"],
    dependencies=[
        Depends(auth_dependencies.validate_access_token),
        Security(auth_dependencies.check_scopes, scopes=["profile"]),
    ],
)
router.include_router(
    gear_components_router.router,
    prefix=core_config.ROOT_PATH + "/gear_components",
    tags=["gear_components"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    gears_router.router,
    prefix=core_config.ROOT_PATH + "/gears",
    tags=["gears"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    health_router.router,
    prefix=core_config.ROOT_PATH + "/health",
    tags=["health"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    health_sleep_router.router,
    prefix=core_config.ROOT_PATH + "/health/sleep",
    tags=["health_sleep"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    health_weight_router.router,
    prefix=core_config.ROOT_PATH + "/health/weight",
    tags=["health_weight"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    health_steps_router.router,
    prefix=core_config.ROOT_PATH + "/health/steps",
    tags=["health_steps"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    health_fasting_router.router,
    prefix=core_config.ROOT_PATH + "/health/fasting",
    tags=["health_fasting"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    health_poop_router.router,
    prefix=core_config.ROOT_PATH + "/health/poop",
    tags=["health_poop"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    health_targets_router.router,
    prefix=core_config.ROOT_PATH + "/health/targets",
    tags=["health_targets"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    health_water_router.router,
    prefix=core_config.ROOT_PATH + "/health/water",
    tags=["health_water"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    identity_providers_router.router,
    prefix=core_config.ROOT_PATH + "/idp",
    tags=["identity_providers"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    notifications_router.router,
    prefix=core_config.ROOT_PATH + "/notifications",
    tags=["notifications"],
    dependencies=[
        Depends(auth_dependencies.validate_access_token),
        Security(auth_dependencies.check_scopes, scopes=["profile"]),
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
        Depends(auth_dependencies.validate_access_token),
        Security(auth_dependencies.check_scopes, scopes=["profile"]),
    ],
)
router.include_router(
    server_settings_router.router,
    prefix=core_config.ROOT_PATH + "/server_settings",
    tags=["server_settings"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    auth_sessions_router.router,
    prefix=core_config.ROOT_PATH + "/sessions",
    tags=["sessions"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
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
        Depends(auth_dependencies.validate_access_token),
        Security(auth_dependencies.check_scopes, scopes=["profile"]),
    ],
)
router.include_router(
    user_goals_router.router,
    prefix=core_config.ROOT_PATH + "/profile/goals",
    tags=["profile"],
    dependencies=[
        Depends(auth_dependencies.validate_access_token),
        Security(auth_dependencies.check_scopes, scopes=["profile"]),
    ],
)
router.include_router(
    auth_api_keys_router.router,
    prefix=core_config.ROOT_PATH + "/profile/api_keys",
    tags=["api_keys"],
    dependencies=[
        Depends(auth_dependencies.validate_access_token),
        Security(auth_dependencies.check_scopes, scopes=["profile"]),
    ],
)
router.include_router(
    users_router.router,
    prefix=core_config.ROOT_PATH + "/users",
    tags=["users"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
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
    prefix=core_config.ROOT_PATH + "/public/activities/{activity_id}",
    tags=["public_activities_laps"],
    dependencies=[Depends(activities_dependencies.validate_activity_id)],
)
router.include_router(
    activity_sets_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities/{activity_id}",
    tags=["public_activity_sets"],
    dependencies=[Depends(activities_dependencies.validate_activity_id)],
)
router.include_router(
    activity_streams_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities/{activity_id}",
    tags=["public_activity_streams"],
    dependencies=[Depends(activities_dependencies.validate_activity_id)],
)
router.include_router(
    activity_workout_steps_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities/{activity_id}",
    tags=["public_activity_workout_steps"],
    dependencies=[Depends(activities_dependencies.validate_activity_id)],
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
