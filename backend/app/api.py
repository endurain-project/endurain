"""Aggregate application routers under the API root."""

from fastapi import APIRouter, Depends, Security

import core.config as core_config
import core.router as core_router

# Alphabetized router imports
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
import modules.auth.account_security.devices_router as auth_devices_router
import modules.auth.account_security.identity_links_router as auth_idp_profile_router
import modules.auth.account_security.mfa_router as auth_mfa_profile_router
import modules.auth.account_security.public_router as auth_password_change_router
import modules.auth.account_security.sessions_router as auth_sessions_profile_router
import modules.auth.authentication.public_router as auth_router
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_providers.router as identity_providers_router
import modules.auth.onboarding.public_router as onboarding_public_router
import modules.auth.password_reset_tokens.public_router as password_reset_tokens_router
import modules.auth.sessions.router as auth_sessions_router
import modules.auth.sign_up_tokens.public_router as sign_up_tokens_router
import modules.followers.blocks_router as followers_blocks_router
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
import modules.jobs.router as jobs_router
import modules.notifications.router as notifications_router
import modules.server_settings.logs_router as server_settings_logs_router
import modules.server_settings.public_router as server_settings_public_router
import modules.server_settings.router as server_settings_router
import modules.strava.router as strava_router
import modules.users.users.photo_router as users_photo_router
import modules.users.users.router as users_router
import modules.users.users_default_gear.router as user_default_gear_router
import modules.users.users_goals.router as user_goals_router
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

#: The server the OpenAPI document states. Every path in it already starts with the API root, so the server is the
#: origin the document was loaded from.
OPENAPI_SERVERS = [{"url": "/", "description": "This server. Every path starts with the API root, `/api/v1`."}]

#: What each tag groups, as the OpenAPI document and the API reference show it.
OPENAPI_TAGS = [
    {"name": "activities", "description": "Activities: list, read, edit, delete, import and upload."},
    {"name": "activity_detail", "description": "An activity with the first page of its laps, sets and steps."},
    {"name": "activity_exercise_titles", "description": "Exercise titles of strength activities."},
    {"name": "activity_laps", "description": "Laps of an activity."},
    {"name": "activity_media", "description": "Photos and other media attached to an activity."},
    {"name": "activity_sets", "description": "Performed workout sets of an activity."},
    {"name": "activity_streams", "description": "Per-sample data of an activity: heart rate, power, cadence, pace."},
    {"name": "activity_summaries", "description": "Totals of activities over a period."},
    {"name": "activity_workout_steps", "description": "Planned workout steps of an activity."},
    {"name": "api-keys", "description": "API keys of the signed-in user."},
    {"name": "auth", "description": "Sign in, sign out, refresh, multi-factor authentication and SSO."},
    {"name": "core", "description": "Server metadata and health."},
    {"name": "followers", "description": "Follow requests, followers and following."},
    {"name": "garmin", "description": "Link a Garmin Connect account and poll the link."},
    {"name": "gear_components", "description": "Components of a gear item, such as a chain or tyres."},
    {"name": "gears", "description": "Bikes, shoes and other gear."},
    {"name": "health", "description": "The health dashboard."},
    {"name": "health_fasting", "description": "Fasting records."},
    {"name": "health_poop", "description": "Bowel movement records."},
    {"name": "health_sleep", "description": "Sleep records."},
    {"name": "health_steps", "description": "Daily step counts."},
    {"name": "health_targets", "description": "Health targets of the signed-in user."},
    {"name": "health_water", "description": "Water intake records."},
    {"name": "health_weight", "description": "Weight and body composition records."},
    {"name": "jobs", "description": "Background jobs: read one by id or list your own."},
    {"name": "identity_providers", "description": "Administration of SSO identity providers."},
    {"name": "identity_providers_public", "description": "Public SSO sign-in flow and provider icons."},
    {"name": "notifications", "description": "Notifications of the signed-in user."},
    {"name": "password_reset_tokens", "description": "Request and use a password reset."},
    {"name": "profile", "description": "The signed-in user's profile, goals, default gear, sessions and export."},
    {"name": "public_activities", "description": "Activities shared publicly, readable without signing in."},
    {"name": "public_activities_laps", "description": "Laps of a publicly shared activity."},
    {"name": "public_activity_detail", "description": "A publicly shared activity with its children."},
    {"name": "public_activity_exercise_titles", "description": "Exercise titles of a publicly shared activity."},
    {"name": "public_activity_sets", "description": "Sets of a publicly shared activity."},
    {"name": "public_activity_streams", "description": "Streams of a publicly shared activity."},
    {"name": "public_activity_workout_steps", "description": "Workout steps of a publicly shared activity."},
    {"name": "public_onboarding", "description": "First-run setup of a new server."},
    {"name": "public_server_settings", "description": "Server settings visible without signing in."},
    {"name": "server_settings", "description": "Administration of server settings and logs."},
    {"name": "sessions", "description": "Administration of user sessions."},
    {"name": "sign_up_tokens", "description": "Sign-up by email verification."},
    {"name": "strava", "description": "Link a Strava account and import its gear."},
    {"name": "users", "description": "Users: list, read, edit, create, delete and their photos."},
    {"name": "websocket", "description": "Tickets to open the notification websocket."},
]

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
    auth_password_change_router.router,
    prefix=core_config.ROOT_PATH + "/auth",
    tags=["auth"],
)
router.include_router(
    followers_blocks_router.router,
    prefix=core_config.ROOT_PATH + "/profile/blocked-users",
    tags=["followers"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    followers_router.router,
    prefix=core_config.ROOT_PATH + "/profile/follow-requests",
    tags=["followers"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    jobs_router.router,
    prefix=core_config.ROOT_PATH + "/jobs",
    tags=["jobs"],
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
        Security(auth_dependencies.check_scopes, scopes=["account"]),
    ],
)
router.include_router(
    password_reset_tokens_router.router,
    prefix=core_config.ROOT_PATH + "/public",
    tags=["password_reset_tokens"],
)
_PROFILE_SECURITY_DEPENDENCIES = [
    Depends(auth_dependencies.validate_access_token),
    Security(auth_dependencies.check_scopes, scopes=["account:security"]),
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
    dependencies=_PROFILE_SECURITY_DEPENDENCIES,
)
router.include_router(
    auth_mfa_profile_router.router,
    prefix=core_config.ROOT_PATH + "/profile/mfa",
    tags=["profile"],
    dependencies=_PROFILE_SECURITY_DEPENDENCIES,
)
router.include_router(
    auth_idp_profile_router.router,
    prefix=core_config.ROOT_PATH + "/profile/identity-providers",
    tags=["profile"],
    dependencies=_PROFILE_SECURITY_DEPENDENCIES,
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
    prefix=core_config.ROOT_PATH + "/public",
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
    auth_devices_router.router,
    prefix=core_config.ROOT_PATH + "/profile/devices",
    tags=["profile"],
    dependencies=_PROFILE_SECURITY_DEPENDENCIES,
)
router.include_router(
    auth_api_keys_router.router,
    prefix=core_config.ROOT_PATH + "/profile/api-keys",
    tags=["api-keys"],
    dependencies=_PROFILE_SECURITY_DEPENDENCIES,
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
# Resources owned by a user, served as ``/users/{user_id}/<resource>``.
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
    prefix=core_config.ROOT_PATH + "/auth",
    tags=["auth"],
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
    core_router.router,
    tags=["core"],
)
