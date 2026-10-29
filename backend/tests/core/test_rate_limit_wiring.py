"""End-to-end coverage for the rate-limit wiring.

``backend/conftest.py`` turns the limiter off for the whole run so rate-limited
routes can be exercised directly. That leaves one thing unproven: whether the
tiers are actually attached to the endpoints that need them. A decorator on the
wrong function, at the wrong tier, or missing entirely would pass every other
test in the suite and only be discovered in production.

So this module asserts three things:

* the *manifest* — each sensitive endpoint carries the tier it is supposed to,
  read from the limiter's own registry rather than from the source text;
* the *completeness* of that manifest — every decorated endpoint in the tree is
  listed, so the list cannot silently fall behind the code; and
* the *behaviour* — a route decorated at a tier really does answer ``429`` with
  the RFC 9457 problem document once the cap is passed, with the limiter enabled
  exactly as the application enables it.
"""

import ast
import pathlib
import time
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import OctKey
from limits import parse as parse_limit
from slowapi.errors import RateLimitExceeded

import core.rate_limit as core_rate_limit
import modules.activities.activity.public_router as activity_public_router
import modules.activities.activity.router as activity_router
import modules.activities.activity.summary_router as activity_summary_router
import modules.activities.activity_detail.public_router as activity_detail_public_router
import modules.activities.activity_exercise_titles.public_router as activity_exercise_titles_public_router
import modules.activities.activity_ingestion.router as ingestion_router
import modules.activities.activity_laps.public_router as activity_laps_public_router
import modules.activities.activity_media.public_router as activity_media_public_router
import modules.activities.activity_media.router as activity_media_router
import modules.activities.activity_sets.public_router as activity_sets_public_router
import modules.activities.activity_streams.public_router as activity_streams_public_router
import modules.activities.activity_streams.router as activity_streams_router
import modules.activities.activity_thumbnail.public_router as activity_thumbnail_public_router
import modules.activities.activity_workout_steps.public_router as activity_workout_steps_public_router
import modules.auth.account_security.api_keys_router as auth_api_keys_router
import modules.auth.account_security.identity_links_router as auth_idp_profile_router
import modules.auth.account_security.mfa_router as auth_mfa_profile_router
import modules.auth.account_security.sessions_router as auth_sessions_profile_router
import modules.auth.authentication.public_router as auth_router
import modules.auth.authentication.sso_public_router as sso_public_router
import modules.auth.identity_providers.public_router as idp_public_router
import modules.auth.identity_providers.router as identity_providers_router
import modules.auth.password_reset_tokens.public_router as password_reset_router
import modules.auth.sessions.router as auth_sessions_router
import modules.auth.sign_up_tokens.public_router as sign_up_tokens_router
import modules.followers.router as followers_router
import modules.followers.user_router as followers_user_router
import modules.garmin.router as garmin_router
import modules.gears.gear.router as gear_router
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
import modules.users.users_default_gear.router as users_default_gear_router
import modules.users.users_goals.router as users_goals_router
import modules.users.users_profile.router as users_profile_router
import modules.websocket.router as websocket_router


def _registered_limits(func) -> list[str]:
    """Return the limit strings slowapi recorded for an endpoint.

    slowapi keys its registry by ``module.qualname``, so this reads the same
    entry the middleware consults at request time rather than re-deriving it. The
    stored form is the parsed one (``"10 per 1 minute"``), which is why the
    expected tier is parsed too rather than string-compared.

    Args:
        func: The decorated endpoint function.

    Returns:
        The configured limit strings, empty when the endpoint carries no tier.
    """
    name = f"{func.__module__}.{func.__name__}"
    return [str(limit.limit) for limit in core_rate_limit.limiter._route_limits.get(name, [])]


# Every endpoint carrying a tier, with the tier it must carry. This is not an
# opt-in list: ``test_every_decorated_endpoint_is_in_the_manifest`` walks the
# source tree and fails when a decorated route is missing from it, so a new
# sensitive endpoint cannot be added without also being asserted here.
_TIERED_ENDPOINTS = [
    pytest.param(auth_router.login_for_access_token, core_rate_limit.SENSITIVE, id="login"),
    pytest.param(auth_router.verify_mfa_and_login, core_rate_limit.SENSITIVE, id="mfa-verify"),
    pytest.param(auth_router.refresh_token, core_rate_limit.WRITE, id="token-refresh"),
    pytest.param(auth_router.logout, core_rate_limit.WRITE, id="logout"),
    pytest.param(sign_up_tokens_router.signup, core_rate_limit.SENSITIVE, id="signup"),
    pytest.param(sign_up_tokens_router.verify_email, core_rate_limit.SENSITIVE, id="verify-email"),
    pytest.param(
        password_reset_router.request_password_reset,
        core_rate_limit.SENSITIVE,
        id="password-reset-request",
    ),
    pytest.param(
        password_reset_router.confirm_password_reset,
        core_rate_limit.SENSITIVE,
        id="password-reset-confirm",
    ),
    pytest.param(server_settings_router.send_test_email, core_rate_limit.SENSITIVE, id="server-settings-test-email"),
    pytest.param(server_settings_router.edit_server_settings, core_rate_limit.WRITE, id="server-settings-edit"),
    pytest.param(server_settings_router.edit_mail_settings, core_rate_limit.WRITE, id="server-settings-edit-mail"),
    pytest.param(server_settings_router.upload_login_photo, core_rate_limit.UPLOAD, id="server-settings-upload-login"),
    pytest.param(server_settings_router.delete_login_photo, core_rate_limit.WRITE, id="server-settings-delete-login"),
    pytest.param(server_settings_logs_router.clear_logs, core_rate_limit.WRITE, id="server-settings-clear-logs"),
    pytest.param(idp_public_router.initiate_login, core_rate_limit.SENSITIVE, id="oidc-initiate"),
    pytest.param(idp_public_router.handle_callback, core_rate_limit.SENSITIVE, id="oidc-callback"),
    pytest.param(
        sso_public_router.exchange_tokens_for_session,
        core_rate_limit.SENSITIVE,
        id="oidc-token-exchange",
    ),
    pytest.param(identity_providers_router.create_identity_provider, core_rate_limit.WRITE, id="idp-create"),
    pytest.param(identity_providers_router.update_identity_provider, core_rate_limit.WRITE, id="idp-update"),
    pytest.param(identity_providers_router.delete_identity_provider, core_rate_limit.WRITE, id="idp-delete"),
    pytest.param(
        auth_idp_profile_router.generate_link_token,
        core_rate_limit.SENSITIVE,
        id="sso-link-token",
    ),
    pytest.param(
        auth_mfa_profile_router.generate_mfa_backup_codes,
        core_rate_limit.SENSITIVE,
        id="mfa-backup-codes",
    ),
    pytest.param(auth_api_keys_router.create_user_api_key, core_rate_limit.SENSITIVE, id="api-key-create"),
    pytest.param(auth_api_keys_router.revoke_user_api_key, core_rate_limit.SENSITIVE, id="api-key-revoke"),
    pytest.param(auth_api_keys_router.delete_user_api_key, core_rate_limit.SENSITIVE, id="api-key-delete"),
    pytest.param(
        auth_idp_profile_router.delete_my_identity_provider,
        core_rate_limit.SENSITIVE,
        id="sso-unlink",
    ),
    pytest.param(users_router.create_user, core_rate_limit.SENSITIVE, id="user-create"),
    pytest.param(users_router.upload_user_image, core_rate_limit.UPLOAD, id="user-image-upload"),
    pytest.param(users_router.edit_user, core_rate_limit.WRITE, id="user-edit"),
    pytest.param(users_router.approve_user, core_rate_limit.WRITE, id="user-approve"),
    pytest.param(users_router.edit_user_password, core_rate_limit.SENSITIVE, id="user-password-reset"),
    pytest.param(users_router.lookup_user_by_email, core_rate_limit.SENSITIVE, id="user-email-lookup"),
    pytest.param(users_router.delete_user_photo, core_rate_limit.WRITE, id="user-photo-delete"),
    pytest.param(users_router.delete_user, core_rate_limit.SENSITIVE, id="user-delete"),
    pytest.param(users_router.delete_user_identity_provider, core_rate_limit.WRITE, id="user-idp-unlink"),
    pytest.param(users_profile_router.upload_profile_image, core_rate_limit.UPLOAD, id="profile-image-upload"),
    pytest.param(users_profile_router.edit_user, core_rate_limit.WRITE, id="profile-edit"),
    pytest.param(users_profile_router.edit_profile_email, core_rate_limit.SENSITIVE, id="profile-email-change"),
    pytest.param(users_profile_router.export_profile_data, core_rate_limit.SENSITIVE, id="profile-export"),
    pytest.param(users_profile_router.download_profile_export, core_rate_limit.SENSITIVE, id="profile-export-download"),
    pytest.param(users_profile_router.edit_profile_privacy_settings, core_rate_limit.WRITE, id="profile-privacy-edit"),
    pytest.param(users_profile_router.edit_profile_password, core_rate_limit.SENSITIVE, id="profile-password-change"),
    pytest.param(users_profile_router.delete_profile_photo, core_rate_limit.WRITE, id="profile-photo-delete"),
    pytest.param(
        auth_sessions_profile_router.delete_profile_other_sessions,
        core_rate_limit.WRITE,
        id="profile-sessions-revoke-others",
    ),
    pytest.param(
        auth_sessions_profile_router.delete_profile_session, core_rate_limit.WRITE, id="profile-session-delete"
    ),
    pytest.param(auth_sessions_router.read_sessions_user, core_rate_limit.EXPENSIVE_READ, id="admin-sessions-read"),
    pytest.param(auth_sessions_router.delete_session_user, core_rate_limit.WRITE, id="admin-session-delete"),
    pytest.param(auth_sessions_router.delete_sessions_user, core_rate_limit.WRITE, id="admin-sessions-delete"),
    pytest.param(users_profile_router.import_profile_data, core_rate_limit.UPLOAD, id="profile-import"),
    pytest.param(users_profile_router.delete_my_account, core_rate_limit.SENSITIVE, id="profile-account-delete"),
    pytest.param(auth_mfa_profile_router.setup_mfa, core_rate_limit.SENSITIVE, id="mfa-setup"),
    pytest.param(auth_mfa_profile_router.enable_mfa, core_rate_limit.SENSITIVE, id="mfa-enable"),
    pytest.param(auth_mfa_profile_router.disable_mfa, core_rate_limit.SENSITIVE, id="mfa-disable"),
    pytest.param(auth_mfa_profile_router.verify_mfa, core_rate_limit.SENSITIVE, id="profile-mfa-verify"),
    pytest.param(users_goals_router.create_user_goal, core_rate_limit.WRITE, id="goal-create"),
    pytest.param(users_goals_router.update_user_goal, core_rate_limit.WRITE, id="goal-update"),
    pytest.param(users_goals_router.delete_user_goal, core_rate_limit.WRITE, id="goal-delete"),
    pytest.param(users_default_gear_router.edit_user_default_gear, core_rate_limit.WRITE, id="default-gear-edit"),
    pytest.param(
        ingestion_router.create_activity_with_uploaded_file,
        core_rate_limit.UPLOAD,
        id="activity-upload",
    ),
    pytest.param(
        ingestion_router.create_bulk_import_from_archive,
        core_rate_limit.UPLOAD,
        id="activity-bulk-import-archive",
    ),
    pytest.param(
        ingestion_router.create_bulk_import_from_folder,
        core_rate_limit.UPLOAD,
        id="activity-bulk-import-folder",
    ),
    pytest.param(strava_router.import_bikes_from_strava_export, core_rate_limit.UPLOAD, id="strava-import-bikes"),
    pytest.param(strava_router.strava_link, core_rate_limit.WRITE, id="strava-link"),
    pytest.param(strava_router.strava_set_user_client, core_rate_limit.WRITE, id="strava-set-client"),
    pytest.param(strava_router.strava_begin_state, core_rate_limit.WRITE, id="strava-begin-state"),
    pytest.param(strava_router.strava_clear_user_state, core_rate_limit.WRITE, id="strava-clear-state"),
    pytest.param(strava_router.strava_retrieve_gear, core_rate_limit.PROVIDER_SYNC, id="strava-retrieve-gear"),
    pytest.param(strava_router.strava_unlink, core_rate_limit.WRITE, id="strava-unlink"),
    pytest.param(strava_router.import_shoes_from_strava_export, core_rate_limit.UPLOAD, id="strava-import-shoes"),
    pytest.param(ingestion_router.refresh_activities, core_rate_limit.PROVIDER_SYNC, id="provider-refresh"),
    pytest.param(
        strava_router.strava_retrieve_activities_days, core_rate_limit.PROVIDER_SYNC, id="strava-retrieve-activities"
    ),
    pytest.param(
        garmin_router.garminconnect_retrieve_activities_days,
        core_rate_limit.PROVIDER_SYNC,
        id="garmin-retrieve-activities",
    ),
    pytest.param(garmin_router.garminconnect_retrieve_gear, core_rate_limit.PROVIDER_SYNC, id="garmin-retrieve-gear"),
    pytest.param(
        garmin_router.garminconnect_retrieve_health_days, core_rate_limit.PROVIDER_SYNC, id="garmin-retrieve-health"
    ),
    pytest.param(garmin_router.garminconnect_link, core_rate_limit.WRITE, id="garmin-link"),
    pytest.param(garmin_router.garminconnect_mfa_code, core_rate_limit.WRITE, id="garmin-mfa"),
    pytest.param(garmin_router.garminconnect_unlink, core_rate_limit.WRITE, id="garmin-unlink"),
    pytest.param(activity_media_router.create_activity_media, core_rate_limit.UPLOAD, id="media-upload"),
    pytest.param(activity_media_router.delete_activity_media, core_rate_limit.WRITE, id="media-delete"),
    pytest.param(activity_router.edit_activity, core_rate_limit.WRITE, id="activity-edit"),
    pytest.param(activity_router.edit_activities, core_rate_limit.WRITE, id="activity-bulk-edit"),
    pytest.param(activity_router.delete_activity, core_rate_limit.WRITE, id="activity-delete"),
    pytest.param(websocket_router.issue_ws_ticket, core_rate_limit.WRITE, id="websocket-ticket"),
    pytest.param(followers_user_router.follow_user, core_rate_limit.WRITE, id="follow-user"),
    pytest.param(followers_router.accept_follow_request, core_rate_limit.WRITE, id="accept-follow-request"),
    pytest.param(followers_router.reject_follow_request, core_rate_limit.WRITE, id="reject-follow-request"),
    pytest.param(followers_user_router.delete_follow_relationship, core_rate_limit.WRITE, id="unfollow"),
    pytest.param(health_fasting_router.create_health_fasting, core_rate_limit.WRITE, id="health-fasting-create"),
    pytest.param(health_fasting_router.edit_health_fasting, core_rate_limit.WRITE, id="health-fasting-edit"),
    pytest.param(health_fasting_router.complete_health_fasting, core_rate_limit.WRITE, id="health-fasting-complete"),
    pytest.param(health_fasting_router.delete_health_fasting, core_rate_limit.WRITE, id="health-fasting-delete"),
    pytest.param(health_poop_router.create_health_poop, core_rate_limit.WRITE, id="health-poop-create"),
    pytest.param(health_poop_router.edit_health_poop, core_rate_limit.WRITE, id="health-poop-edit"),
    pytest.param(health_poop_router.delete_health_poop, core_rate_limit.WRITE, id="health-poop-delete"),
    pytest.param(health_sleep_router.create_health_sleep, core_rate_limit.WRITE, id="health-sleep-create"),
    pytest.param(health_sleep_router.edit_health_sleep, core_rate_limit.WRITE, id="health-sleep-edit"),
    pytest.param(health_sleep_router.delete_health_sleep, core_rate_limit.WRITE, id="health-sleep-delete"),
    pytest.param(health_steps_router.create_health_steps, core_rate_limit.WRITE, id="health-steps-create"),
    pytest.param(health_steps_router.edit_health_steps, core_rate_limit.WRITE, id="health-steps-edit"),
    pytest.param(health_steps_router.delete_health_steps, core_rate_limit.WRITE, id="health-steps-delete"),
    pytest.param(health_targets_router.update_health_targets, core_rate_limit.WRITE, id="health-targets-update"),
    pytest.param(health_water_router.create_health_water, core_rate_limit.WRITE, id="health-water-create"),
    pytest.param(health_water_router.edit_health_water, core_rate_limit.WRITE, id="health-water-edit"),
    pytest.param(health_water_router.delete_health_water, core_rate_limit.WRITE, id="health-water-delete"),
    pytest.param(health_weight_router.create_health_weight, core_rate_limit.WRITE, id="health-weight-create"),
    pytest.param(health_weight_router.edit_health_weight, core_rate_limit.WRITE, id="health-weight-edit"),
    pytest.param(health_weight_router.delete_health_weight, core_rate_limit.WRITE, id="health-weight-delete"),
    pytest.param(gear_router.create_gear, core_rate_limit.WRITE, id="gear-create"),
    pytest.param(gear_router.edit_gear, core_rate_limit.WRITE, id="gear-edit"),
    pytest.param(gear_router.delete_gear, core_rate_limit.WRITE, id="gear-delete"),
    pytest.param(gear_components_router.create_gear_component, core_rate_limit.WRITE, id="gear-component-create"),
    pytest.param(gear_components_router.edit_gear_component, core_rate_limit.WRITE, id="gear-component-edit"),
    pytest.param(gear_components_router.delete_component_gear, core_rate_limit.WRITE, id="gear-component-delete"),
    pytest.param(notifications_router.mark_notification_as_read, core_rate_limit.WRITE, id="notification-mark-read"),
    pytest.param(
        notifications_router.mark_all_notifications_as_read, core_rate_limit.WRITE, id="notification-mark-all-read"
    ),
    pytest.param(
        activity_summary_router.read_activity_summary, core_rate_limit.EXPENSIVE_READ, id="activity-summary-read"
    ),
    pytest.param(
        activity_streams_router.list_activity_streams, core_rate_limit.EXPENSIVE_READ, id="activity-streams-list"
    ),
    pytest.param(
        activity_streams_router.read_activity_stream, core_rate_limit.EXPENSIVE_READ, id="activity-stream-read"
    ),
    pytest.param(
        activity_streams_public_router.list_public_activity_streams,
        core_rate_limit.EXPENSIVE_PUBLIC_READ,
        id="public-activity-streams-list",
    ),
    pytest.param(
        activity_streams_public_router.read_public_activity_stream,
        core_rate_limit.EXPENSIVE_PUBLIC_READ,
        id="public-activity-stream-read",
    ),
    pytest.param(
        health_dashboard_router.read_health_daily_stats, core_rate_limit.EXPENSIVE_READ, id="health-dashboard"
    ),
    pytest.param(users_goals_router.get_user_goals_results, core_rate_limit.EXPENSIVE_READ, id="goals-results"),
    pytest.param(activity_public_router.read_public_activity, core_rate_limit.PUBLIC_READ, id="public-activity"),
    pytest.param(activity_laps_public_router.list_public_activity_laps, core_rate_limit.PUBLIC_READ, id="public-laps"),
    pytest.param(
        activity_detail_public_router.read_public_activity_detail,
        core_rate_limit.PUBLIC_READ,
        id="public-activity-detail",
    ),
    pytest.param(activity_sets_public_router.list_public_activity_sets, core_rate_limit.PUBLIC_READ, id="public-sets"),
    pytest.param(
        activity_workout_steps_public_router.list_public_activity_workout_steps,
        core_rate_limit.PUBLIC_READ,
        id="public-workout-steps",
    ),
    pytest.param(
        activity_exercise_titles_public_router.list_public_activity_exercise_titles,
        core_rate_limit.PUBLIC_READ,
        id="public-exercise-titles",
    ),
    pytest.param(
        activity_media_public_router.read_activity_media_file, core_rate_limit.PUBLIC_READ, id="public-media-blob"
    ),
    pytest.param(
        activity_thumbnail_public_router.read_activity_thumbnail, core_rate_limit.PUBLIC_READ, id="public-thumbnail"
    ),
    pytest.param(users_public_router.read_users_id, core_rate_limit.PUBLIC_READ, id="public-user"),
    pytest.param(users_photo_router.read_user_photo, core_rate_limit.PUBLIC_READ, id="user-photo"),
    pytest.param(
        server_settings_public_router.read_public_server_settings,
        core_rate_limit.PUBLIC_READ,
        id="public-server-settings",
    ),
    pytest.param(
        server_settings_public_router.list_tile_maps_templates, core_rate_limit.PUBLIC_READ, id="public-tile-templates"
    ),
    pytest.param(server_settings_public_router.read_login_photo, core_rate_limit.PUBLIC_READ, id="public-login-photo"),
]


@pytest.mark.parametrize(("endpoint", "expected_tier"), _TIERED_ENDPOINTS)
def test_the_endpoint_carries_its_tier(endpoint, expected_tier):
    """A missing or mistyped decorator is invisible to every other test."""
    assert str(parse_limit(expected_tier)) in _registered_limits(endpoint)


_APP_ROOT = pathlib.Path("app")


def _decorated_endpoints() -> set[str]:
    """Return every endpoint decorated with a rate-limit tier, from the source.

    Read off the AST rather than the limiter registry: the registry only holds
    what the current test session happened to import, so a decorated route in an
    unimported module would look like it does not exist. The filesystem cannot
    be under-imported.

    Returns:
        Dotted ``module.function`` names, keyed the way slowapi keys its registry.
    """
    found: set[str] = set()
    for path in sorted(_APP_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        module = ".".join(path.relative_to(_APP_ROOT).with_suffix("").parts)
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and ast.unparse(decorator.func).endswith("limiter.limit"):
                    found.add(f"{module}.{node.name}")
    return found


def test_every_decorated_endpoint_is_in_the_manifest():
    """The manifest cannot fall behind the code.

    A hand-maintained list of sensitive routes is only as good as the last person
    who remembered to append to it, and this one had already drifted: ``signup``,
    ``verify_email`` and the MFA backup-code route were all rate-limited in the
    application and absent here, so deleting their decorators would have broken
    no test. Deriving the expected set from the source makes the omission the
    failure instead of the silence.
    """
    listed = {f"{param.values[0].__module__}.{param.values[0].__name__}" for param in _TIERED_ENDPOINTS}

    assert _decorated_endpoints() - listed == set(), (
        "Rate-limited endpoint(s) missing from _TIERED_ENDPOINTS. Add each one "
        "with the tier it must carry, so removing its decorator fails a test."
    )


@pytest.fixture
def enabled_limiter() -> Iterator[None]:
    """Re-enable the limiter (and clear its buckets) for one test."""
    core_rate_limit.limiter.enabled = True
    core_rate_limit.limiter.reset()
    try:
        yield
    finally:
        core_rate_limit.limiter.reset()
        core_rate_limit.limiter.enabled = False


def _app_with(tier: str, probe_name: str) -> FastAPI:
    """Build a one-route app wired exactly as ``main.create_app`` wires the limiter.

    Args:
        tier: The tier constant to decorate the probe route with.
        probe_name: A name unique to this app. slowapi keys its registry by
            ``module.funcname``, so two probes sharing a name would stack their
            limits and the tightest one would silently win.

    Returns:
        The configured app.
    """
    app = FastAPI()
    app.state.limiter = core_rate_limit.limiter
    app.add_exception_handler(
        RateLimitExceeded,
        core_rate_limit.rate_limit_exceeded_handler,  # type: ignore[arg-type]
    )
    app.add_middleware(core_rate_limit.RateLimitMiddleware)

    def probe(request: Request) -> dict[str, bool]:
        return {"ok": True}

    probe.__name__ = probe_name
    app.post("/probe")(core_rate_limit.limiter.limit(tier)(probe))
    return app


def _burst(client: TestClient, token: str, count: int) -> list[int]:
    return [client.post("/probe", headers={"Authorization": f"Bearer {token}"}).status_code for _ in range(count)]


@pytest.mark.parametrize(
    ("tier", "cap"),
    [
        (core_rate_limit.SENSITIVE, 10),
        (core_rate_limit.UPLOAD, 20),
        (core_rate_limit.PROVIDER_SYNC, 6),
    ],
    ids=["sensitive", "upload", "provider-sync"],
)
def test_a_tier_actually_refuses_past_its_cap(enabled_limiter, tier, cap):
    """Proves the tier constants bound real traffic, not just that they parse."""
    client = TestClient(_app_with(tier, f"probe_cap_{cap}"))

    statuses = _burst(client, f"token-cap-{cap}", cap + 1)

    assert statuses[:cap] == [200] * cap
    assert statuses[cap] == 429


def test_the_refusal_is_a_problem_document_with_retry_after(enabled_limiter):
    """Clients back off on ``Retry-After``; a bare 429 body would not tell them how long."""
    client = TestClient(_app_with(core_rate_limit.PROVIDER_SYNC, "probe_problem_doc"))

    statuses = _burst(client, "token-problem-doc", 7)
    assert statuses[-1] == 429

    refused = client.post("/probe", headers={"Authorization": "Bearer token-problem-doc"})
    assert refused.status_code == 429
    assert refused.headers["content-type"].startswith("application/problem+json")
    assert refused.json()["title"] == "Too Many Requests"
    assert "Retry-After" in refused.headers


def test_buckets_are_per_caller_not_global(enabled_limiter, monkeypatch):
    """One user exhausting a tier must not lock everyone else out.

    The limiter only buckets by token when the signature verifies, so the callers
    carry real tokens signed with a key the limiter is pointed at.
    """
    key = OctKey.import_key("rate-limit-test-secret-key-min-32-chars")
    monkeypatch.setattr(core_rate_limit, "_jwt_verification_key", lambda: key)
    noisy, quiet = (
        jwt.encode({"alg": "HS256"}, {"sub": sub, "typ": "access", "exp": int(time.time()) + 300}, key)
        for sub in ("noisy", "quiet")
    )
    client = TestClient(_app_with(core_rate_limit.PROVIDER_SYNC, "probe_per_caller"))

    assert _burst(client, noisy, 7)[-1] == 429
    assert _burst(client, quiet, 1) == [200]
