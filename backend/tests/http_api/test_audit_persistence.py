"""Audit rows over HTTP: written with the business change, kept for a refusal, free of values, and append-only."""

import json
import os
import socket
import typing
from enum import Enum

import jasil.audit as jasil_audit
import pyotp
import pytest
import sqlalchemy as sa
import sqlalchemy.exc as sa_exc
from fastapi.testclient import TestClient
from jasil.audit.models import AuditLog

import core.config as core_config
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.server_settings.schema as server_settings_schema
from tests._factories.contract import make_activity
from tests._factories.users import PASSWORD, make_admin, make_user

_API = core_config.ROOT_PATH
_STEP_UP = {"step_up": {"current_password": PASSWORD}}
_NEW_PASSWORD = "Brand-New-Password-5678!"


def _user(committed_sessions, make=make_user, **fields):
    with committed_sessions() as db:
        user = make(db, **fields)
        db.commit()
    return user


def _rows(committed_sessions, *action_ids: str) -> list[AuditLog]:
    """Read the audit rows of the given actions (all rows when none is named), oldest first, detached."""
    statement = sa.select(AuditLog).order_by(AuditLog.occurred_at, AuditLog.id)
    if action_ids:
        statement = statement.where(AuditLog.action_id.in_(action_ids))
    with committed_sessions() as db:
        rows = list(db.scalars(statement))
        db.expunge_all()
    return rows


def _only(committed_sessions, action_id: str) -> AuditLog:
    rows = _rows(committed_sessions, action_id)
    assert len(rows) == 1, f"{action_id}: {[(r.outcome, r.details) for r in rows]}"
    return rows[0]


def _etag(client: TestClient, path: str) -> str:
    return client.get(f"{_API}{path}").headers["ETag"]


def _web(app, **headers: str) -> TestClient:
    """An anonymous web client; it carries the allowed origin a cookie route demands."""
    return TestClient(app, headers={"X-Client-Type": "web", "Origin": app.state.cors_allow_origins[0], **headers})


def _resolving_to_a_public_address(monkeypatch, host: str) -> None:
    """Make one host name resolve to a public address, as the DNS the identity-provider check asks is a third party."""
    real = socket.getaddrinfo

    def resolve(name, *args, **kwargs):
        if name == host:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        return real(name, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolve)


class TestSuccessWritesOneRowWithTheChange:
    def test_a_follow_the_target_accepts_is_audited_once_for_the_target(self, committed_sessions, sign_in):
        follower, target = _user(committed_sessions), _user(committed_sessions)
        assert sign_in(follower).client.post(f"{_API}/users/{target.id}/followers").status_code == 201

        response = sign_in(target).client.post(f"{_API}/profile/follow-requests/{follower.id}/accept")

        assert response.status_code == 200, response.text
        row = _only(committed_sessions, "followers.follow.accept")
        assert (row.outcome, row.actor_type, row.actor_id) == ("success", "user", str(target.id))
        assert (row.target_type, row.target_id, row.target_owner_id) == ("user", str(follower.id), str(target.id))

    def test_blocking_a_user_is_audited_once_and_blocking_again_adds_no_row(self, committed_sessions, sign_in):
        blocker, blocked = _user(committed_sessions), _user(committed_sessions)
        client = sign_in(blocker).client

        first = client.put(f"{_API}/profile/blocked-users/{blocked.id}")
        again = client.put(f"{_API}/profile/blocked-users/{blocked.id}")

        assert (first.status_code, again.status_code) == (204, 204)
        row = _only(committed_sessions, "followers.block.add")
        assert (row.actor_id, row.target_id, row.target_owner_id) == (str(blocker.id), str(blocked.id), str(blocker.id))

    def test_an_administrator_creating_a_user_is_audited_with_the_new_account_as_target(
        self, committed_sessions, sign_in
    ):
        admin = _user(committed_sessions, make_admin)
        body = {
            "name": "New Person",
            "username": "new-person",
            "email": "new.person@example.org",
            "access_type": "regular",
            "active": True,
            "password": _NEW_PASSWORD,
        }

        response = sign_in(admin).client.post(f"{_API}/users", json=body)

        assert response.status_code == 201, response.text
        row = _only(committed_sessions, "users.user.create")
        assert (row.outcome, row.actor_id) == ("success", str(admin.id))
        assert (row.target_type, row.target_id, row.target_owner_id) == (
            "user",
            response.json()["id"],
        ) * 1 + (response.json()["id"],)
        assert row.details == {"method": "admin", "invited": False, "access_type": "regular"}

    def test_an_administrator_editing_a_user_is_audited_with_the_field_names_only(self, committed_sessions, sign_in):
        admin, user = _user(committed_sessions, make_admin), _user(committed_sessions)
        client = sign_in(admin).client

        response = client.patch(
            f"{_API}/users/{user.id}",
            json={"name": "Renamed Person"},
            headers={"If-Match": _etag(client, f"/users/{user.id}")},
        )

        assert response.status_code == 200, response.text
        row = _only(committed_sessions, "users.user.update")
        assert (row.actor_id, row.target_id, row.target_owner_id) == (str(admin.id), str(user.id), str(user.id))
        assert row.details == {"changed_fields": ["name"]}

    def test_a_privacy_change_is_audited_with_the_changed_field_names(self, committed_sessions, sign_in):
        user = _user(committed_sessions)
        client = sign_in(user).client

        response = client.patch(
            f"{_API}/profile/privacy",
            json={"hide_activity_map": True},
            headers={"If-Match": _etag(client, "/profile/privacy")},
        )

        assert response.status_code == 200, response.text
        row = _only(committed_sessions, "users.privacy.update")
        assert (row.actor_id, row.target_id) == (str(user.id), str(user.id))
        assert row.details == {"changed_fields": ["hide_activity_map"]}

    def test_a_profile_export_request_is_audited_for_the_owner(self, committed_sessions, sign_in):
        user = _user(committed_sessions)

        response = sign_in(user).client.post(f"{_API}/profile/export", json=_STEP_UP)

        assert response.status_code == 202, response.text
        row = _only(committed_sessions, "users.profile_export.request")
        assert (row.outcome, row.actor_id, row.target_owner_id) == ("success", str(user.id), str(user.id))

    def test_a_username_change_is_audited_without_the_new_name(self, committed_sessions, sign_in):
        user = _user(committed_sessions)

        response = sign_in(user).client.post(
            f"{_API}/profile/username/change", json={"username": "renamed-user", **_STEP_UP}
        )

        assert response.status_code == 200, response.text
        row = _only(committed_sessions, "users.username.change")
        assert (row.actor_id, row.target_id) == (str(user.id), str(user.id))
        assert row.details == {"other_sessions_revoked": True}

    def test_ending_the_other_sessions_when_there_are_none_records_no_session_revoke(self, committed_sessions, sign_in):
        """``audit-trail.md``: stage nothing when nothing changed."""
        user = _user(committed_sessions)

        response = sign_in(user).client.post(
            f"{_API}/profile/username/change", json={"username": "renamed-user", **_STEP_UP}
        )

        assert response.status_code == 200, response.text
        assert _rows(committed_sessions, "auth.session.revoke") == []

    def test_ending_another_session_records_one_session_revoke_with_its_count(self, committed_sessions, sign_in):
        user = _user(committed_sessions)
        signed_in = sign_in(user)
        sign_in(user)

        response = signed_in.client.post(
            f"{_API}/profile/username/change", json={"username": "renamed-user", **_STEP_UP}
        )

        assert response.status_code == 200, response.text
        assert _only(committed_sessions, "auth.session.revoke").details == {"sessions_revoked": 1}

    def test_a_password_change_is_audited_with_the_count_of_sessions_it_ended(self, committed_sessions, sign_in):
        user = _user(committed_sessions)
        signed_in = sign_in(user)
        sign_in(user)

        response = signed_in.client.post(
            f"{_API}/profile/password/change", json={"password": _NEW_PASSWORD, **_STEP_UP}
        )

        assert response.status_code == 204, response.text
        row = _only(committed_sessions, "auth.password.change")
        assert (row.actor_id, row.target_id) == (str(user.id), str(user.id))
        assert row.details == {"sessions_revoked": 1}

    def test_creating_an_api_key_is_audited_with_its_scopes_and_the_key_as_credential(
        self, committed_sessions, sign_in
    ):
        user = _user(committed_sessions)

        response = sign_in(user).client.post(
            f"{_API}/profile/api-keys", json={"name": "ci", "scopes": ["activities:read"], **_STEP_UP}
        )

        assert response.status_code == 201, response.text
        row = _only(committed_sessions, "auth.api_key.create")
        assert (row.actor_id, row.target_type, row.target_id) == (str(user.id), "api_key", response.json()["id"])
        assert row.details == {"scopes": ["activities:read"]}

    def test_a_sign_in_is_audited_as_a_success_with_the_user_as_actor(self, app, committed_sessions):
        user = _user(committed_sessions)

        response = _web(app).post(f"{_API}/auth/login", data={"username": user.username, "password": PASSWORD})

        assert response.status_code == 200, response.text
        row = _only(committed_sessions, "auth.session.login")
        assert (row.outcome, row.actor_type, row.actor_id) == ("success", "user", str(user.id))
        assert row.details == {"method": "password", "mfa": False, "reason": None, "new_device": False}

    def test_signing_out_is_audited_for_the_session_owner(self, app, committed_sessions, sign_in):
        user = _user(committed_sessions)
        signed_in = sign_in(user)
        web = _web(app)
        web.cookies.set(authentication_dependencies.REFRESH_TOKEN_COOKIE_NAME, signed_in.refresh_token)

        response = web.post(f"{_API}/auth/logout")

        assert response.status_code == 200, response.text
        row = _only(committed_sessions, "auth.session.logout")
        assert (row.outcome, row.actor_id) == ("success", str(user.id))

    def test_ending_the_other_sessions_is_audited_with_their_count(self, committed_sessions, sign_in):
        user = _user(committed_sessions)
        current = sign_in(user)
        sign_in(user)

        response = current.client.post(f"{_API}/profile/sessions/revoke", params={"keep_current": True})

        assert response.status_code == 204, response.text
        row = _only(committed_sessions, "auth.session.revoke")
        assert (row.actor_id, row.details) == (str(user.id), {"sessions_revoked": 1})

    def test_storing_strava_client_credentials_is_audited_without_details(self, committed_sessions, sign_in):
        user = _user(committed_sessions)
        client = sign_in(user).client

        response = client.put(
            f"{_API}/strava/client",
            json={"client_id": 4242, "client_secret": "strava-client-secret", **_STEP_UP},
            headers={"If-Match": _etag(client, "/profile")},
        )

        assert response.status_code == 204, response.text
        row = _only(committed_sessions, "strava.client.update")
        assert (row.actor_id, row.target_owner_id, row.details) == (str(user.id), str(user.id), None)

    def test_unlinking_garmin_is_audited_for_the_owner(self, committed_sessions, sign_in):
        user = _user(committed_sessions)

        response = sign_in(user).client.post(f"{_API}/garmin/unlink", json=_STEP_UP)

        assert response.status_code == 204, response.text
        row = _only(committed_sessions, "garmin.account.unlink")
        assert (row.outcome, row.actor_id, row.target_id) == ("success", str(user.id), str(user.id))

    def test_changing_server_settings_is_audited_with_the_changed_field_names(self, committed_sessions, sign_in):
        admin = _user(committed_sessions, make_admin)
        client = sign_in(admin).client
        current = client.get(f"{_API}/server-settings")
        editable = {
            n: v for n, v in current.json().items() if n in server_settings_schema.ServerSettingsEdit.model_fields
        }
        body = {**editable, "num_records_per_page": 40, "step_up": None}

        response = client.put(f"{_API}/server-settings", json=body, headers={"If-Match": current.headers["ETag"]})

        assert response.status_code == 200, response.text
        row = _only(committed_sessions, "server_settings.settings.update")
        assert row.actor_id == str(admin.id)
        assert row.details == {"changed_fields": ["num_records_per_page"]}

    def test_clearing_the_server_logs_is_audited_for_the_administrator(self, committed_sessions, sign_in):
        admin = _user(committed_sessions, make_admin)

        response = sign_in(admin).client.post(f"{_API}/server-settings/logs/clear", json=_STEP_UP)

        assert response.status_code == 204, response.text
        row = _only(committed_sessions, "server_settings.logs.clear")
        assert (row.outcome, row.actor_id) == ("success", str(admin.id))

    def test_creating_an_identity_provider_is_audited_with_its_type_only(
        self, committed_sessions, sign_in, monkeypatch
    ):
        _resolving_to_a_public_address(monkeypatch, "idp.example.org")
        admin = _user(committed_sessions, make_admin)
        body = {
            "name": "Company SSO",
            "slug": "company-sso",
            "client_id": "client-id-1",
            "client_secret": "client-secret-1",
            "provider_type": "oidc",
            "issuer_url": "https://idp.example.org",
            "step_up": _STEP_UP["step_up"],
        }

        response = sign_in(admin).client.post(f"{_API}/identity-providers", json=body)

        assert response.status_code == 201, response.text
        row = _only(committed_sessions, "auth.identity_provider.create")
        assert (row.actor_id, row.target_id) == (str(admin.id), response.json()["id"])
        assert row.details == {"provider_type": "oidc"}

    def test_changing_an_activitys_visibility_is_audited_for_the_owner(self, committed_sessions, sign_in):
        user = _user(committed_sessions)
        with committed_sessions() as db:
            activity = make_activity(db, user.id)
            db.commit()

        response = sign_in(user).client.patch(
            f"{_API}/activities/{activity.id}", json={"visibility": "followers"}, headers={"If-Match": '"1"'}
        )

        assert response.status_code == 200, response.text
        row = _only(committed_sessions, "activities.visibility.update")
        assert (row.actor_id, row.target_type, row.target_id) == (str(user.id), "activity", str(activity.id))
        assert row.details == {"changed_fields": ["visibility"]}

    def test_enabling_mfa_and_signing_in_with_a_backup_code_are_audited(self, app, committed_sessions, sign_in):
        user = _user(committed_sessions)
        client = sign_in(user).client
        secret = client.post(f"{_API}/profile/mfa/setup").json()["secret"]
        enabled = client.post(f"{_API}/profile/mfa/enable", json={"totp_code": pyotp.TOTP(secret).now(), **_STEP_UP})
        assert enabled.status_code == 200, enabled.text
        web = _web(app)
        challenge = web.post(f"{_API}/auth/login", data={"username": user.username, "password": PASSWORD}).json()

        response = web.post(
            f"{_API}/auth/mfa/verify",
            json={"mfa_challenge": challenge["mfa_challenge"], "mfa_code": enabled.json()["codes"][0]},
        )

        assert response.status_code == 200, response.text
        assert _only(committed_sessions, "auth.mfa.enable").details == {"sessions_revoked": 0}
        used = _only(committed_sessions, "auth.backup_codes.use")
        assert (used.outcome, used.actor_id, used.details) == ("success", str(user.id), {"remaining_codes": 9})
        logins = _rows(committed_sessions, "auth.session.login")
        assert [(r.outcome, r.details["mfa"]) for r in logins] == [("success", True)]

    def test_a_bulk_import_from_the_server_folder_is_audited_with_its_source_before_the_files_are_counted(
        self, committed_sessions, sign_in
    ):
        user = _user(committed_sessions)
        folder = core_config.bulk_import_dir_for(user.id)
        os.makedirs(folder)
        with open(os.path.join(folder, "run.gpx"), "w") as file:
            file.write("<gpx/>")

        response = sign_in(user).client.post(f"{_API}/activities/bulk-import/folder")

        assert response.status_code == 202, response.text
        row = _only(committed_sessions, "activities.import.request")
        assert (row.outcome, row.actor_id, row.target_owner_id) == ("success", str(user.id), str(user.id))
        assert row.details == {"source": "server_directory", "file_count": None}


class TestARefusalIsKeptThoughTheRequestFails:
    def test_a_wrong_password_is_audited_as_a_failure_for_the_account(self, app, committed_sessions):
        user = _user(committed_sessions)

        response = _web(app).post(
            f"{_API}/auth/login", data={"username": user.username, "password": "not-the-password"}
        )

        assert response.status_code == 401
        row = _only(committed_sessions, "auth.session.login")
        assert (row.outcome, row.actor_type, row.target_id) == ("failure", "anonymous", str(user.id))
        assert row.details == {"method": "password", "mfa": False, "reason": "invalid_credentials", "new_device": False}

    def test_repeated_wrong_passwords_are_audited_as_a_lockout_with_the_attempt_count(self, app, committed_sessions):
        user = _user(committed_sessions)
        web = _web(app)

        for _ in range(5):
            assert (
                web.post(f"{_API}/auth/login", data={"username": user.username, "password": "nope"}).status_code == 401
            )

        assert len(_rows(committed_sessions, "auth.session.login")) == 5
        lockout = _only(committed_sessions, "auth.lockout.apply")
        assert (lockout.outcome, lockout.actor_type, lockout.details) == (
            "success",
            "anonymous",
            {"counter": "login", "failed_attempts": 5},
        )

    def test_a_missing_scope_is_audited_as_denied_for_the_caller(self, committed_sessions, sign_in):
        user = _user(committed_sessions)

        response = sign_in(user).client.get(f"{_API}/users/{user.id}/identity-providers")

        assert response.status_code == 403
        row = _only(committed_sessions, "auth.scope.denied")
        assert (row.outcome, row.actor_id, row.details) == (
            "denied",
            str(user.id),
            {"missing_scopes": ["users:read-all"]},
        )

    def test_a_refused_first_run_onboarding_is_audited_as_denied(self, client, committed_sessions):
        _user(committed_sessions)
        body = {
            "name": "X",
            "username": "late-comer",
            "email": "late@example.org",
            "password": _NEW_PASSWORD,
            "token": "t",
        }

        response = client.post(f"{_API}/public/onboarding", json=body)

        assert response.status_code == 409
        row = _only(committed_sessions, "auth.onboarding.refuse")
        assert (row.outcome, row.actor_type, row.details) == ("denied", "anonymous", {"reason": "account_exists"})

    def test_a_failed_step_up_is_audited_and_the_guarded_change_does_not_happen(self, committed_sessions, sign_in):
        user = _user(committed_sessions)

        response = sign_in(user).client.post(
            f"{_API}/profile/api-keys",
            json={"name": "ci", "scopes": ["activities:read"], "step_up": {"current_password": "wrong-password"}},
        )

        assert response.status_code == 403
        failed = _only(committed_sessions, "auth.step_up.verify")
        assert (failed.outcome, failed.actor_id) == ("failure", str(user.id))
        assert failed.details == {"method": "password", "reason": "invalid_credentials"}
        assert _rows(committed_sessions, "auth.api_key.create") == []

    def test_an_unknown_password_reset_token_is_audited_as_a_failure(self, client, committed_sessions):
        response = client.post(
            f"{_API}/public/password-reset/confirm", json={"token": "x" * 43, "password": _NEW_PASSWORD}
        )

        assert response.status_code in (400, 422), response.text
        row = _only(committed_sessions, "auth.password.reset")
        assert (row.outcome, row.actor_type, row.target_id) == ("failure", "anonymous", None)

    def test_an_unknown_sign_up_token_is_audited_as_a_failure(self, client, committed_sessions):
        response = client.post(f"{_API}/public/sign-up/confirm", json={"token": "x" * 43, "password": _NEW_PASSWORD})

        assert response.status_code in (400, 404), response.text
        row = _only(committed_sessions, "auth.sign_up.confirm")
        assert (row.outcome, row.actor_type) == ("failure", "anonymous")


class TestAFailedBusinessWriteLeavesNoSuccessRow:
    def test_a_stale_write_is_refused_and_nothing_is_audited(self, committed_sessions, sign_in):
        user = _user(committed_sessions)
        client = sign_in(user).client

        response = client.patch(
            f"{_API}/profile/privacy", json={"hide_activity_map": True}, headers={"If-Match": '"99"'}
        )

        assert response.status_code == 412
        assert _rows(committed_sessions, "users.privacy.update") == []

    def test_a_username_an_administrator_cannot_give_is_refused_and_nothing_is_audited(
        self, committed_sessions, sign_in
    ):
        admin, user, other = _user(committed_sessions, make_admin), _user(committed_sessions), _user(committed_sessions)
        client = sign_in(admin).client

        response = client.patch(
            f"{_API}/users/{user.id}",
            json={"username": other.username, **_STEP_UP},
            headers={"If-Match": _etag(client, f"/users/{user.id}")},
        )

        assert response.status_code == 409
        assert _rows(committed_sessions, "users.user.update") == []

    def test_a_commit_the_database_refuses_discards_the_row_staged_with_the_change(
        self, app, committed_sessions, sign_in
    ):
        user = _user(committed_sessions)
        signed_in = sign_in(user)
        client = TestClient(app, headers=dict(signed_in.client.headers), raise_server_exceptions=False)
        assert (
            client.patch(f"{_API}/profile", json={"name": "First Name"}, headers={"If-Match": '"1"'}).status_code == 200
        )
        with committed_sessions() as db:
            db.execute(
                sa.text(
                    "CREATE FUNCTION refuse_commit() RETURNS trigger LANGUAGE plpgsql AS "
                    "$$ BEGIN RAISE EXCEPTION 'commit refused'; END $$"
                )
            )
            db.execute(
                sa.text(
                    "CREATE CONSTRAINT TRIGGER refuse_boom AFTER UPDATE ON users DEFERRABLE INITIALLY DEFERRED "
                    "FOR EACH ROW WHEN (NEW.name = 'Boom') EXECUTE FUNCTION refuse_commit()"
                )
            )
            db.commit()

        response = client.patch(
            f"{_API}/profile", json={"name": "Boom"}, headers={"If-Match": _etag(client, "/profile")}
        )

        assert response.status_code == 500
        assert [row.details for row in _rows(committed_sessions, "users.profile.update")] == [
            {"changed_fields": ["name"]}
        ]
        assert client.get(f"{_API}/profile").json()["name"] == "First Name"


class TestDetailsHoldNoValues:
    def test_no_stored_row_holds_a_password_token_code_key_secret_or_address_a_flow_carried(
        self, app, committed_sessions, sign_in, monkeypatch
    ):
        _resolving_to_a_public_address(monkeypatch, "idp.example.org")
        admin = _user(committed_sessions, make_admin)
        user = _user(committed_sessions)
        signed_in = sign_in(user)
        admin_client = sign_in(admin).client
        client = signed_in.client
        secrets: dict[str, str] = {
            "the user's password": PASSWORD,
            "the user's address": user.email,
            "the user's username": user.username,
            "the access token": signed_in.access_token,
            "the refresh token": signed_in.refresh_token,
        }

        def carry(label: str, value: str) -> None:
            secrets[label] = value

        wrong = "wrong-Password-4711!"
        carry("a wrong password", wrong)
        _web(app).post(f"{_API}/auth/login", data={"username": user.username, "password": wrong})
        client.post(
            f"{_API}/profile/api-keys",
            json={"name": "ci", "scopes": ["activities:read"], "step_up": {"current_password": wrong}},
        )
        key = client.post(f"{_API}/profile/api-keys", json={"name": "ci", "scopes": ["activities:read"], **_STEP_UP})
        carry("an API key", key.json()["key"])
        carry("an API key name", "ci-key-name-unique")
        client.post(
            f"{_API}/profile/api-keys", json={"name": "ci-key-name-unique", "scopes": ["activities:read"], **_STEP_UP}
        )
        carry("a client secret", "strava-client-secret-5521")
        client.put(
            f"{_API}/strava/client",
            json={"client_id": 987654321, "client_secret": "strava-client-secret-5521", **_STEP_UP},
            headers={"If-Match": _etag(client, "/profile")},
        )
        carry("a new address", "changed.address@example.org")
        client.post(f"{_API}/profile/email/change", json={"email": "changed.address@example.org", **_STEP_UP})
        carry("a new username", "changed-username-77")
        client.post(f"{_API}/profile/username/change", json={"username": "changed-username-77", **_STEP_UP})
        carry("a new name", "Changed Display Name")
        client.patch(
            f"{_API}/profile", json={"name": "Changed Display Name"}, headers={"If-Match": _etag(client, "/profile")}
        )
        carry("a new password", _NEW_PASSWORD)
        carry("a created user's address", "created.person@example.org")
        carry("a created user's name", "Created Person Name")
        admin_client.post(
            f"{_API}/users",
            json={
                "name": "Created Person Name",
                "username": "created-person",
                "email": "created.person@example.org",
                "access_type": "regular",
                "active": True,
                "password": _NEW_PASSWORD,
            },
        )
        carry("a provider secret", "idp-client-secret-9931")
        admin_client.post(
            f"{_API}/identity-providers",
            json={
                "name": "Company SSO",
                "slug": "company-sso",
                "client_id": "idp-client-id-9931",
                "client_secret": "idp-client-secret-9931",
                "provider_type": "oidc",
                "issuer_url": "https://idp.example.org",
                "step_up": _STEP_UP["step_up"],
            },
        )
        totp = client.post(f"{_API}/profile/mfa/setup").json()["secret"]
        carry("the TOTP secret", totp)
        enabled = client.post(f"{_API}/profile/mfa/enable", json={"totp_code": pyotp.TOTP(totp).now(), **_STEP_UP})
        assert enabled.status_code == 200, enabled.text
        for index, code in enumerate(enabled.json()["codes"]):
            carry(f"backup code {index}", code)
        client.post(
            f"{_API}/profile/password/change",
            json={
                "password": _NEW_PASSWORD,
                **_STEP_UP,
                "step_up": {"current_password": PASSWORD, "mfa_code": pyotp.TOTP(totp).now()},
            },
        )

        rows = _rows(committed_sessions)

        assert {row.action_id for row in rows} >= {
            "auth.api_key.create",
            "auth.step_up.verify",
            "auth.session.login",
            "strava.client.update",
            "users.email.change_request",
            "users.username.change",
            "users.profile.update",
            "users.user.create",
            "auth.identity_provider.create",
            "auth.mfa.enable",
        }
        leaks = [
            f"{row.action_id}.{column}: {label}"
            for row in rows
            for column, text in _texts(row).items()
            for label, value in secrets.items()
            if value in text
        ]
        assert leaks == []


def _texts(row: AuditLog) -> dict[str, str]:
    """Every column of an audit row as text, the JSON column serialised, for a search for literal values."""
    return {
        column.name: json.dumps(value, default=str) if isinstance(value, dict | list) else str(value)
        for column in AuditLog.__table__.columns
        for value in [getattr(row, column.name)]
        if value is not None
    }


def _details_models() -> list[tuple[str, type]]:
    """The details model of every application action, read from the catalog the running app registered."""
    return [
        (action.id, action.details_model)
        for action in jasil_audit.get_catalog()
        if action.details_model is not None and not action.id.startswith("audit.")
    ]


#: The free-text fields a details model may declare, with why each holds names the code defines, never a value.
_NAME_FIELDS = {
    "changed_fields": "the names of columns",
    "scopes": "scope names from the scope catalogue",
    "missing_scopes": "scope names from the scope catalogue",
    "access_type": "the access tier, a fixed vocabulary",
    "credential_type": "how the caller authenticated, a fixed vocabulary",
}
#: Field names that would carry a person's or a secret's value.
_VALUE_NAMES = {
    "email",
    "username",
    "name",
    "password",
    "token",
    "code",
    "secret",
    "url",
    "filename",
    "file_name",
    "key",
}


class TestTheCatalogAllowsNoValues:
    def test_every_details_model_with_fields_forbids_extra_keys_and_declares_a_schema_version(self, app):
        models = _details_models()

        broken = [
            action_id
            for action_id, model in models
            if model.model_fields
            and (
                model.model_config.get("extra") != "forbid"
                or not isinstance(model.SCHEMA_VERSION, int)
                or model.SCHEMA_VERSION < 1
            )
        ]
        assert len(models) > 50
        assert broken == []

    def test_a_details_field_is_a_flag_count_id_timestamp_enum_or_a_declared_name_list(self, app):
        free_text: list[str] = []
        for action_id, model in _details_models():
            for name, field in model.model_fields.items():
                if name in _VALUE_NAMES:
                    free_text.append(f"{action_id}.{name}: named like a value")
                if _holds_free_text(field.annotation) and name not in _NAME_FIELDS:
                    free_text.append(f"{action_id}.{name}: {field.annotation}")

        assert free_text == [], "A details field of free text must be a declared name list (_NAME_FIELDS)"


def _holds_free_text(annotation: object) -> bool:
    """Whether a plain ``str`` appears in an annotation, outside an enum."""
    if annotation is str:
        return True
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return False
    return any(_holds_free_text(argument) for argument in typing.get_args(annotation))


class TestTheTrailIsAppendOnly:
    @pytest.fixture
    def stored_row(self, app, committed_sessions):
        user = _user(committed_sessions)
        _web(app).post(f"{_API}/auth/login", data={"username": user.username, "password": PASSWORD})
        return _only(committed_sessions, "auth.session.login")

    @pytest.mark.parametrize(
        "statement",
        ["UPDATE jasil_audit_log SET outcome = 'denied'", "DELETE FROM jasil_audit_log", "TRUNCATE jasil_audit_log"],
        ids=["update", "delete", "truncate"],
    )
    def test_the_database_refuses_to_change_or_remove_a_row(self, committed_sessions, stored_row, statement):
        with committed_sessions() as db, pytest.raises(sa_exc.DBAPIError):
            db.execute(sa.text(statement))
            db.commit()

        assert _only(committed_sessions, "auth.session.login").outcome == "success"
