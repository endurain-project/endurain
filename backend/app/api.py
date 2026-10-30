"""Aggregate application routers under the API root."""

from fastapi import APIRouter, Depends, Security

import core.config as core_config
import core.router as core_router

# Alphabetized router imports
import modules.activities.activity.gear_router as activity_gear_router
import modules.activities.activity.public_router as activity_public_router
import modules.activities.activity.router as activity_router
import modules.activities.activity.summary_router as activity_summary_router
import modules.activities.activity.user_router as activity_user_router
import modules.activities.activity_detail.public_router as activity_detail_public_router
import modules.activities.activity_detail.router as activity_detail_router
import modules.activities.activity_ingestion.router as activity_ingestion_router
import modules.activities.activity_laps.public_router as activity_laps_public_router
import modules.activities.activity_laps.router as activity_laps_router
import modules.activities.activity_media.public_router as activity_media_public_router
import modules.activities.activity_media.router as activity_media_router
import modules.activities.activity_sets.public_router as activity_sets_public_router
import modules.activities.activity_sets.router as activity_sets_router
import modules.activities.activity_streams.router as activity_streams_router
import modules.activities.activity_thumbnail.public_router as activity_thumbnail_public_router
import modules.auth.account_security.api_keys_router as auth_api_keys_router
import modules.auth.account_security.identity_links_router as auth_idp_profile_router
import modules.auth.account_security.mfa_router as auth_mfa_profile_router
import modules.auth.account_security.sessions_router as auth_sessions_profile_router
import modules.auth.authentication.public_router as auth_router
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_providers.router as identity_providers_router
import modules.auth.onboarding.public_router as onboarding_public_router
import modules.auth.password_reset_tokens.public_router as password_reset_tokens_router
import modules.auth.sessions.router as auth_sessions_router
import modules.auth.sign_up_tokens.public_router as sign_up_tokens_router
import modules.followers.router as followers_router
import modules.followers.user_router as followers_user_router
import modules.garmin.router as garmin_router
import modules.gears.gear.router as gears_router
import modules.gears.gear_components.gear_router as gear_components_gear_router
import modules.gears.gear_components.router as gear_components_router
import modules.health.health_dashboard.router as health_dashboard_router
import modules.health.health_fasting.router as health_fasting_router
import modules.health.health_poop.router as health_poop_router
import modules.health.health_sleep.router as health_sleep_router
import modules.health.health_steps.router as health_steps_router
import modules.health.health_targets.router as health_targets_router
import modules.health.health_water.router as health_water_router
import modules.health.health_weight.router as health_weight_router
import modules.notifications.router as notifications_router
import modules.server_settings.logs_router as server_settings_logs_router
import modules.server_settings.public_router as server_settings_public_router
import modules.server_settings.router as server_settings_router
import modules.strava.router as strava_router
import modules.users.users.photo_router as users_photo_router
import modules.users.users.public_router as users_public_router
import modules.users.users.router as users_router
import modules.users.users_default_gear.router as user_default_gear_router
import modules.users.users_goals.router as user_goals_router
import modules.users.users_profile.browser_redirect_router as profile_browser_redirect_router
import modules.users.users_profile.overview_router as profile_overview_router
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
from modules.auth.authentication import (
    sso_public_router as authentication_sso_public_router,
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
    activity_thumbnail_public_router.router,
    prefix=core_config.ROOT_PATH + "/activities",
    tags=["activities"],
)
# Activity media blobs are token-gated for the same reason and in the same way.
router.include_router(
    activity_media_public_router.router,
    prefix=core_config.ROOT_PATH + "/activities",
    tags=["activity_media"],
)
# So are user profile photos, whose stored name is the user id — the one blob
# kind whose public path was directly enumerable.
router.include_router(
    users_photo_router.router,
    prefix=core_config.ROOT_PATH + "/users",
    tags=["users"],
)
# Literal ``/activities/<name>`` sub-resources, mounted for the same reason as the
# ingestion routers above: they must be matched before the core router's dynamic
# ``/activities/{activity_id}``, which would otherwise swallow "summaries" and
# "exercise-titles" as activity ids and answer 422.
router.include_router(
    activity_summary_router.router,
    prefix=core_config.ROOT_PATH + "/activities/summaries",
    tags=["activity_summaries"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    activity_exercise_titles_router.router,
    prefix=core_config.ROOT_PATH + "/activities/exercise-titles",
    tags=["activity_exercise_titles"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    activity_router.router,
    prefix=core_config.ROOT_PATH + "/activities",
    tags=["activities"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    activity_detail_router.router,
    prefix=core_config.ROOT_PATH + "/activities/{activity_id}",
    tags=["activity_detail"],
    dependencies=[
        Depends(auth_dependencies.validate_access_token),
    ],
)
router.include_router(
    activity_laps_router.router,
    prefix=core_config.ROOT_PATH + "/activities/{activity_id}",
    tags=["activity_laps"],
    dependencies=[
        Depends(auth_dependencies.validate_access_token),
    ],
)
router.include_router(
    activity_media_router.router,
    prefix=core_config.ROOT_PATH + "/activities/{activity_id}",
    tags=["activity_media"],
    dependencies=[
        Depends(auth_dependencies.validate_access_token),
    ],
)
router.include_router(
    activity_sets_router.router,
    prefix=core_config.ROOT_PATH + "/activities/{activity_id}",
    tags=["activity_sets"],
    dependencies=[
        Depends(auth_dependencies.validate_access_token),
    ],
)
router.include_router(
    activity_streams_router.router,
    prefix=core_config.ROOT_PATH + "/activities/{activity_id}",
    tags=["activity_streams"],
    dependencies=[
        Depends(auth_dependencies.validate_access_token),
    ],
)
router.include_router(
    activity_workout_steps_router.router,
    prefix=core_config.ROOT_PATH + "/activities/{activity_id}",
    tags=["activity_workout_steps"],
    dependencies=[
        Depends(auth_dependencies.validate_access_token),
    ],
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
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    garmin_router.router,
    prefix=core_config.ROOT_PATH + "/garmin",
    tags=["garmin"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    gear_components_router.router,
    prefix=core_config.ROOT_PATH + "/gear-components",
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
    activity_gear_router.router,
    prefix=core_config.ROOT_PATH + "/gears",
    tags=["activities"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    gear_components_gear_router.router,
    prefix=core_config.ROOT_PATH + "/gears",
    tags=["gear_components"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    health_dashboard_router.router,
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
    prefix=core_config.ROOT_PATH + "/identity-providers",
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
_PROFILE_DEPENDENCIES = [
    Depends(auth_dependencies.validate_access_token),
    Security(auth_dependencies.check_scopes, scopes=["profile"]),
]
router.include_router(
    profile_router.router,
    prefix=core_config.ROOT_PATH + "/profile",
    tags=["profile"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
# The signed-in user's own sessions, two-step verification and identity provider links are auth's
# to serve; they live under /profile so the API paths are unchanged.
router.include_router(
    auth_sessions_profile_router.router,
    prefix=core_config.ROOT_PATH + "/profile/sessions",
    tags=["profile"],
    dependencies=_PROFILE_DEPENDENCIES,
)
router.include_router(
    auth_mfa_profile_router.router,
    prefix=core_config.ROOT_PATH + "/profile/mfa",
    tags=["profile"],
    dependencies=_PROFILE_DEPENDENCIES,
)
router.include_router(
    auth_idp_profile_router.router,
    prefix=core_config.ROOT_PATH + "/profile/identity-providers",
    tags=["profile"],
    dependencies=_PROFILE_DEPENDENCIES,
)
router.include_router(
    server_settings_router.router,
    prefix=core_config.ROOT_PATH + "/server-settings",
    tags=["server_settings"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    server_settings_logs_router.router,
    prefix=core_config.ROOT_PATH + "/server-settings/logs",
    tags=["server_settings"],
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
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    user_default_gear_router.router,
    prefix=core_config.ROOT_PATH + "/profile/default-gear",
    tags=["profile"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    user_goals_router.router,
    prefix=core_config.ROOT_PATH + "/profile/goals",
    tags=["profile"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    auth_api_keys_router.router,
    prefix=core_config.ROOT_PATH + "/profile/api-keys",
    tags=["api-keys"],
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
    profile_overview_router.router,
    prefix=core_config.ROOT_PATH + "/users",
    tags=["users"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
# Resources owned by a user, served as ``/users/{user_id}/<resource>``. Mounted AFTER the users routers on
# purpose: their literal ``/users/id/...`` and ``/users/username/...`` paths must be matched before the
# ``{user_id}`` segment here would swallow "id" or "username".
router.include_router(
    auth_sessions_router.router,
    prefix=core_config.ROOT_PATH + "/users",
    tags=["sessions"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    activity_user_router.router,
    prefix=core_config.ROOT_PATH + "/users",
    tags=["activities"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    followers_user_router.router,
    prefix=core_config.ROOT_PATH + "/users",
    tags=["followers"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    websocket_router.router,
    prefix=core_config.ROOT_PATH + "/ws",
    tags=["websocket"],
)

# PUBLIC ROUTES (alphabetical order)
router.include_router(
    activity_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities",
    tags=["public_activities"],
)
router.include_router(
    activity_detail_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities/{activity_id}",
    tags=["public_activity_detail"],
)
router.include_router(
    activity_exercise_titles_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities/exercise-titles",
    tags=["public_activity_exercise_titles"],
)
router.include_router(
    activity_laps_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities/{activity_id}",
    tags=["public_activities_laps"],
)
router.include_router(
    activity_sets_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities/{activity_id}",
    tags=["public_activity_sets"],
)
router.include_router(
    activity_streams_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities/{activity_id}",
    tags=["public_activity_streams"],
)
router.include_router(
    activity_workout_steps_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/activities/{activity_id}",
    tags=["public_activity_workout_steps"],
)
router.include_router(
    identity_providers_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/idp",
    tags=["identity_providers_public"],
)
router.include_router(
    authentication_sso_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/idp",
    tags=["identity_providers_public"],
)
router.include_router(
    onboarding_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/onboarding",
    tags=["public_onboarding"],
)
router.include_router(
    server_settings_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/server-settings",
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
