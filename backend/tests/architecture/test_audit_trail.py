"""The audit-trail rules from ``docs/developer-guide/audit-trail.md`` that hold across every module.

A package declares its actions in ``audit_actions.py`` and the composition root registers them. These tests
fail an action file nobody registers, an action nobody writes, an id that names another module, and a write route
nobody decided about: each one either records the actions it is mapped to or is listed with why it records none.
"""

import ast
import importlib
import pathlib

import jasil.audit as jasil_audit
from tests._helpers.routes import MODULES_ROOT, WRITE_METHODS, route_decorators, router_functions

import module_registry as runtime_module_registry

_APP = pathlib.Path("app")
_MODULES_ROOT = _APP / "modules"


def _dotted(path: pathlib.Path) -> str:
    """Return the import path of a file under ``app``, e.g. ``modules.users.users.audit_actions``."""
    return ".".join(path.relative_to(_APP).with_suffix("").parts)


_ACTION_MODULES = tuple(_dotted(path) for path in sorted(_MODULES_ROOT.rglob("audit_actions.py")))


#: Why a write route records no audit action; the routes below cite these, or say why in their own words.
_PERSONAL = "the user's own personal record, not security-relevant"
_ROUTINE = "routine sync or refresh, traced by its events"
_NO_ACCESS = "grants or removes no access: a follow request or its decline"
_MFA_SETUP = "only stores a pending MFA secret; enabling MFA is audited"

#: Router files in which every write is a personal record.
_UNAUDITED_ROUTERS: dict[str, str] = {
    "activities/activity_media/router.py": _PERSONAL,
    "gears/gear/router.py": _PERSONAL,
    "gears/gear_components/router.py": _PERSONAL,
    "health/health_fasting/router.py": _PERSONAL,
    "health/health_poop/router.py": _PERSONAL,
    "health/health_sleep/router.py": _PERSONAL,
    "health/health_steps/router.py": _PERSONAL,
    "health/health_targets/router.py": _PERSONAL,
    "health/health_water/router.py": _PERSONAL,
    "health/health_weight/router.py": _PERSONAL,
    "notifications/router.py": _PERSONAL,
    "users/users_default_gear/router.py": _PERSONAL,
    "users/users_goals/router.py": _PERSONAL,
}

#: Write routes and the audit actions they record, in the request or in the job it queues for what was asked.
_AUDITED_WRITES: dict[tuple[str, str], tuple[str, ...]] = {
    ("activities/activity/router.py", "edit_activities"): ("activities.visibility.bulk_update",),
    ("activities/activity/router.py", "edit_activity"): ("activities.visibility.update",),
    ("activities/activity_ingestion/router.py", "create_bulk_import_from_archive"): ("activities.import.request",),
    ("activities/activity_ingestion/router.py", "create_bulk_import_from_folder"): ("activities.import.request",),
    ("auth/account_security/api_keys_router.py", "create_user_api_key"): (
        "auth.api_key.create",
        "auth.backup_codes.use",
        "auth.lockout.apply",
        "auth.step_up.verify",
    ),
    ("auth/account_security/api_keys_router.py", "delete_user_api_key"): ("auth.api_key.delete",),
    ("auth/account_security/api_keys_router.py", "revoke_user_api_key"): ("auth.api_key.revoke",),
    ("auth/account_security/identity_links_router.py", "delete_my_identity_provider"): (
        "auth.backup_codes.use",
        "auth.identity_link.unlink",
        "auth.lockout.apply",
        "auth.step_up.verify",
    ),
    ("auth/account_security/identity_links_router.py", "start_idp_link"): (
        "auth.backup_codes.use",
        "auth.lockout.apply",
        "auth.step_up.verify",
    ),
    ("auth/account_security/identity_links_router.py", "start_idp_step_up"): ("auth.step_up.verify",),
    ("auth/account_security/mfa_router.py", "disable_mfa"): (
        "auth.backup_codes.use",
        "auth.lockout.apply",
        "auth.mfa.disable",
        "auth.step_up.verify",
    ),
    ("auth/account_security/mfa_router.py", "enable_mfa"): (
        "auth.backup_codes.use",
        "auth.lockout.apply",
        "auth.mfa.enable",
        "auth.step_up.verify",
    ),
    ("auth/account_security/mfa_router.py", "generate_mfa_backup_codes"): (
        "auth.backup_codes.generate",
        "auth.backup_codes.use",
        "auth.lockout.apply",
        "auth.step_up.verify",
    ),
    ("auth/account_security/mfa_router.py", "verify_mfa"): (
        "auth.backup_codes.use",
        "auth.lockout.apply",
        "auth.step_up.verify",
    ),
    ("auth/account_security/sessions_router.py", "delete_profile_other_sessions"): ("auth.session.revoke",),
    ("auth/account_security/sessions_router.py", "delete_profile_session"): ("auth.session.revoke",),
    ("auth/authentication/public_router.py", "login_for_access_token"): ("auth.lockout.apply", "auth.session.login"),
    ("auth/authentication/public_router.py", "logout"): ("auth.session.logout",),
    ("auth/authentication/public_router.py", "refresh_token"): ("auth.session.refresh", "auth.session.refresh_reuse"),
    ("auth/authentication/public_router.py", "verify_mfa_and_login"): (
        "auth.backup_codes.use",
        "auth.lockout.apply",
        "auth.session.login",
    ),
    ("auth/authentication/sso_public_router.py", "exchange_tokens_for_session"): (
        "auth.backup_codes.use",
        "auth.lockout.apply",
        "auth.session.login",
    ),
    ("auth/identity_providers/router.py", "create_identity_provider"): ("auth.identity_provider.create",),
    ("auth/identity_providers/router.py", "delete_identity_provider"): ("auth.identity_provider.delete",),
    ("auth/identity_providers/router.py", "delete_identity_provider_icon"): ("auth.identity_provider.update",),
    ("auth/identity_providers/router.py", "update_identity_provider"): ("auth.identity_provider.update",),
    ("auth/identity_providers/router.py", "upload_identity_provider_icon"): ("auth.identity_provider.update",),
    ("auth/onboarding/public_router.py", "complete_onboarding"): ("users.user.create",),
    ("auth/password_reset_tokens/public_router.py", "confirm_password_reset"): ("auth.password.reset",),
    ("auth/password_reset_tokens/public_router.py", "request_password_reset"): ("auth.password_reset.request",),
    ("auth/sessions/router.py", "delete_session_user"): ("auth.session.revoke",),
    ("auth/sessions/router.py", "delete_sessions_user"): ("auth.session.revoke",),
    ("auth/sign_up_tokens/public_router.py", "signup"): ("users.user.create",),
    ("auth/sign_up_tokens/public_router.py", "verify_email"): ("auth.sign_up.confirm", "users.email.change"),
    ("followers/router.py", "accept_follow_request"): ("followers.follow.accept",),
    ("followers/user_router.py", "delete_follow_relationship"): ("followers.follow.remove",),
    ("garmin/router.py", "garminconnect_link"): ("garmin.account.link",),
    ("garmin/router.py", "garminconnect_unlink"): ("garmin.account.unlink",),
    ("server_settings/logs_router.py", "clear_logs"): ("server_settings.logs.clear",),
    ("server_settings/router.py", "delete_login_photo"): ("server_settings.login_photo.delete",),
    ("server_settings/router.py", "edit_mail_settings"): ("server_settings.mail.update",),
    ("server_settings/router.py", "edit_server_settings"): ("server_settings.settings.update",),
    ("server_settings/router.py", "upload_login_photo"): ("server_settings.login_photo.update",),
    ("strava/router.py", "import_bikes_from_strava_export"): ("strava.gear.import",),
    ("strava/router.py", "import_shoes_from_strava_export"): ("strava.gear.import",),
    ("strava/router.py", "strava_link"): ("strava.account.link",),
    ("strava/router.py", "strava_set_user_client"): ("strava.client.update",),
    ("strava/router.py", "strava_unlink"): ("strava.account.unlink",),
    ("users/users/router.py", "approve_user"): ("users.user.approve",),
    ("users/users/router.py", "create_user"): ("users.user.create",),
    ("users/users/router.py", "delete_user"): ("auth.session.revoke", "users.user.delete"),
    ("users/users/router.py", "delete_user_identity_provider"): ("auth.identity_link.unlink",),
    ("users/users/router.py", "delete_user_photo"): ("users.user.update",),
    ("users/users/router.py", "edit_user"): ("auth.session.revoke", "users.user.update"),
    ("users/users/router.py", "edit_user_password"): ("auth.password.set",),
    ("users/users/router.py", "upload_user_image"): ("users.user.update",),
    ("users/users_profile/router.py", "delete_my_account"): (
        "auth.backup_codes.use",
        "auth.lockout.apply",
        "auth.session.revoke",
        "auth.step_up.verify",
        "users.user.delete",
    ),
    ("users/users_profile/router.py", "edit_profile_email"): (
        "auth.backup_codes.use",
        "auth.lockout.apply",
        "auth.session.revoke",
        "auth.step_up.verify",
        "users.email.change_request",
    ),
    ("users/users_profile/router.py", "edit_profile_password"): (
        "auth.backup_codes.use",
        "auth.lockout.apply",
        "auth.password.change",
        "auth.step_up.verify",
    ),
    ("users/users_profile/router.py", "edit_profile_privacy_settings"): ("users.privacy.update",),
    ("users/users_profile/router.py", "edit_user"): ("users.profile.update",),
    ("users/users_profile/router.py", "export_profile_data"): ("users.profile_export.request",),
    ("users/users_profile/router.py", "import_profile_data"): ("users.profile_import.request",),
}

#: Write routes that record no audit action, with why.
_UNAUDITED_WRITES: dict[tuple[str, str], str] = {
    ("activities/activity/router.py", "delete_activity"): _PERSONAL,
    ("activities/activity_ingestion/router.py", "create_activity_with_uploaded_file"): _PERSONAL,
    ("activities/activity_ingestion/router.py", "refresh_activities"): _ROUTINE,
    ("auth/account_security/mfa_router.py", "setup_mfa"): _MFA_SETUP,
    (
        "auth/sign_up_tokens/public_router.py",
        "resend_verification_email",
    ): "resends the verification email of a pending sign-up; the sign-up is audited when it is confirmed",
    (
        "auth/password_reset_tokens/public_router.py",
        "validate_password_reset_token",
    ): "checks that a reset token is still usable and changes nothing; the reset is audited by confirm_password_reset",
    ("followers/router.py", "reject_follow_request"): _NO_ACCESS,
    ("followers/user_router.py", "follow_user"): _NO_ACCESS,
    (
        "garmin/router.py",
        "garminconnect_mfa_code",
    ): "hands an MFA code to a pending Garmin link; the link itself is audited by garminconnect_link",
    ("garmin/router.py", "garminconnect_retrieve_activities_days"): _ROUTINE,
    ("garmin/router.py", "garminconnect_retrieve_gear"): _ROUTINE,
    ("garmin/router.py", "garminconnect_retrieve_health_days"): _ROUTINE,
    (
        "server_settings/router.py",
        "send_test_email",
    ): "sends a test email to the requesting admin; changes no stored state",
    (
        "strava/router.py",
        "strava_begin_state",
    ): "stores a one-time OAuth correlation state; the link it starts is audited by strava_link",
    (
        "strava/router.py",
        "strava_clear_user_state",
    ): "forgets the user's pending OAuth state; grants or removes no access",
    ("strava/router.py", "strava_retrieve_activities_days"): _ROUTINE,
    ("strava/router.py", "strava_retrieve_gear"): _ROUTINE,
    ("users/users/router.py", "lookup_user_by_email"): "read-only lookup by email address; changes nothing",
    (
        "users/users_profile/router.py",
        "cancel_profile_email_change",
    ): "cancels the user's own pending email change; grants or removes no access",
    ("users/users_profile/router.py", "delete_profile_photo"): _PERSONAL,
    (
        "users/users_profile/router.py",
        "resend_profile_email_change",
    ): "resends the confirmation of a pending email change; the change is audited when requested",
    ("users/users_profile/router.py", "upload_profile_image"): _PERSONAL,
    (
        "websocket/router.py",
        "issue_ws_ticket",
    ): "issues a 30-second single-use WebSocket ticket; grants no standing access",
}


def _written_names() -> set[tuple[str, str]]:
    """Return every ``(audit_actions module, attribute)`` an application file reads, outside the composition root.

    An ``import modules.x.audit_actions as alias`` followed by ``alias.NAME`` counts as a use of ``NAME``.
    """
    used: set[tuple[str, str]] = set()
    for path in sorted(_APP.rglob("*.py")):
        if path.name == "audit_actions.py" or path == _APP / "module_registry.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = {
            alias.asname or alias.name: alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
            if alias.name in _ACTION_MODULES
        }
        used.update(
            (aliases[node.value.id], node.attr)
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases
        )
    return used


class TestAuditActionModules:
    def test_every_audit_actions_file_is_registered_by_a_runtime_module(self):
        registered = [module.audit_actions for module in runtime_module_registry.MODULES]
        unregistered = [
            name
            for name in _ACTION_MODULES
            if not any(actions is importlib.import_module(name).ACTIONS for actions in registered)
        ]

        assert not unregistered, f"Add these to a RuntimeModule's audit_actions in module_registry.py: {unregistered}"

    def test_every_action_is_written_by_application_code(self):
        used = _written_names()
        unused = []
        for name in _ACTION_MODULES:
            module = importlib.import_module(name)
            for action in module.ACTIONS:
                if action.deprecated:
                    continue
                attributes = {attr for attr, value in vars(module).items() if value is action}
                if not any((name, attr) in used for attr in attributes):
                    unused.append(action.id)

        assert not unused, f"Declared but never written; write them or mark them deprecated: {unused}"

    def test_an_action_id_starts_with_its_top_level_module(self):
        misnamed = [
            f"{action.id} (declared in {name})"
            for name in _ACTION_MODULES
            for action in importlib.import_module(name).ACTIONS
            if action.id.split(".")[0] != name.split(".")[1]
        ]

        assert not misnamed, misnamed

    def test_every_action_is_declared_in_its_modules_actions_tuple(self):
        undeclared = [
            f"{name}.{attr}"
            for name in _ACTION_MODULES
            for attr, value in vars(importlib.import_module(name)).items()
            if isinstance(value, jasil_audit.AuditAction) and value not in importlib.import_module(name).ACTIONS
        ]

        assert not undeclared, f"Add these to the module's ACTIONS: {undeclared}"


def _write_routes() -> set[tuple[str, str]]:
    """Return ``(router file, handler)`` for every write route of every converted module."""
    return {
        (path.relative_to(MODULES_ROOT).as_posix(), function.name)
        for path, function in router_functions()
        if any(method in WRITE_METHODS for method, _ in route_decorators(function))
    }


class TestWriteRouteCoverage:
    """Every write route was decided: it records named actions, or it records none for a stated reason.

    The tables cannot see whether the service really writes the row; each module's own ``capture_audit`` tests do.
    """

    def test_every_write_route_is_classified(self):
        unclassified = sorted(
            f"{router}::{handler}"
            for router, handler in _write_routes()
            if (router, handler) not in _AUDITED_WRITES
            and (router, handler) not in _UNAUDITED_WRITES
            and router not in _UNAUDITED_ROUTERS
        )

        assert not unclassified, (
            "Add these write routes to _AUDITED_WRITES with the actions they record, or to _UNAUDITED_WRITES with "
            "why they record none (docs/developer-guide/audit-trail.md):\n  " + "\n  ".join(unclassified)
        )

    def test_every_entry_names_a_write_route_once(self):
        routes = _write_routes()
        entries = [*_AUDITED_WRITES, *_UNAUDITED_WRITES]
        stale = sorted(f"{router}::{handler}" for router, handler in entries if (router, handler) not in routes)
        stale += sorted(router for router in _UNAUDITED_ROUTERS if not any(route[0] == router for route in routes))
        twice = sorted(
            f"{router}::{handler}"
            for router, handler in entries
            if router in _UNAUDITED_ROUTERS
            or ((router, handler) in _AUDITED_WRITES and (router, handler) in _UNAUDITED_WRITES)
        )

        assert not stale, f"These entries name no write route any more: {stale}"
        assert not twice, f"These routes are classified more than once: {twice}"

    def test_a_mapped_route_names_declared_actions(self):
        declared = {action.id for name in _ACTION_MODULES for action in importlib.import_module(name).ACTIONS}
        unknown = sorted({action_id for ids in _AUDITED_WRITES.values() for action_id in ids} - declared)
        empty = sorted(f"{router}::{handler}" for (router, handler), ids in _AUDITED_WRITES.items() if not ids)

        assert not unknown, f"Not declared in any audit_actions.py: {unknown}"
        assert not empty, f"An audited route names at least one action: {empty}"
