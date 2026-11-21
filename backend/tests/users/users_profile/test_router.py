"""The profile routes through the production application: status, headers, bodies, ETags and the full transfers."""

import io
import zipfile
from datetime import UTC, datetime

import jasil.runtime as jasil_runtime
import pytest
from fastapi.testclient import TestClient

import core.config as core_config
import modules.users.users_goals.crud as goals_crud
import modules.users.users_integrations.integration_service as integrations_integration
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.export_service as export_service
import modules.users.users_profile.import_service as import_service
import modules.users.users_profile.subscribers as profile_subscribers
import modules.users.users_profile.transfer_pool as transfer_pool
from tests._factories.profile import png, profile_archive
from tests._factories.server_settings import edit_mail_settings
from tests._factories.users import PASSWORD, make_admin, make_user

_API = core_config.ROOT_PATH
_PROFILE = f"{_API}/profile"
_STEP_UP = {"step_up": {"current_password": PASSWORD}}
_NEW_PASSWORD = "A completely new passphrase 2026!"


@pytest.fixture
def user(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db, name="Ada", city="Porto", username="ada")
        db.commit()
    return created


@pytest.fixture
def me(sign_in, user):
    return sign_in(user)


@pytest.fixture
def roomy_memory(monkeypatch):
    """The pytest process holds what earlier tests allocated, which the memory limit is not about."""
    exports = export_service.ExportPerformanceConfig(max_memory_mb=1_000_000)
    imports = import_service.ImportPerformanceConfig(max_memory_mb=1_000_000)
    monkeypatch.setattr(export_service.ExportPerformanceConfig, "get_auto_config", classmethod(lambda cls: exports))
    monkeypatch.setattr(import_service.ImportPerformanceConfig, "get_auto_config", classmethod(lambda cls: imports))


@pytest.fixture
def running_transfers(roomy_memory):
    """Deliver the transfer events to the subscribers that run them, and wait for the pool when asked."""
    profile_subscribers.register_bus_subscribers(jasil_runtime.get_active_platform().events)

    def drain():
        transfer_pool.pool.submit(lambda: None).result(timeout=60)

    return drain


def _etag(response):
    return response.headers["ETag"]


class TestReadProfile:
    def test_the_profile_carries_the_users_version_as_its_etag(self, me, user):
        response = me.client.get(_PROFILE)

        assert response.status_code == 200
        assert _etag(response) == f'"{response.json()["version"]}"'
        body = response.json()
        assert (body["id"], body["username"], body["city"]) == (str(user.id), "ada", "Porto")
        assert (body["is_strava_linked"], body["has_local_password"], body["mfa_enabled"]) == (False, True, False)

    def test_intact_and_revoked_strava_access_tell_the_day_the_data_is_deleted(self, me, user, committed_sessions):
        assert me.client.get(_PROFILE).json()["strava_revoked_at"] is None

        with committed_sessions() as db:
            integrations_integration.link_strava_account(
                user.id, {"access_token": "a", "refresh_token": "r", "expires_at": 1_900_000_000}, db
            )
            refresh = integrations_integration.require_user_integrations(user.id, db).strava_refresh_token
            integrations_integration.unlink_strava_tokens_if_refresh_token(
                user.id, refresh, db, revoked_at=datetime(2025, 3, 1, tzinfo=UTC)
            )
            db.commit()

        body = me.client.get(_PROFILE).json()
        assert body["is_strava_linked"] is False
        assert body["strava_revoked_at"].startswith("2025-03-01")
        assert body["strava_data_deletion_at"].startswith("2025-03-08")


class TestEditProfile:
    def test_the_edit_answers_with_the_profile_and_its_new_etag(self, me):
        version = me.client.get(_PROFILE).json()["version"]

        response = me.client.patch(
            _PROFILE, json={"city": "Lisbon", "height": 181}, headers={"If-Match": f'"{version}"'}
        )

        assert response.status_code == 200
        assert (response.json()["city"], response.json()["height"]) == ("Lisbon", 181)
        assert _etag(response) == f'"{version + 1}"'
        assert me.client.get(_PROFILE).json()["city"] == "Lisbon"

    def test_a_stale_version_is_refused_and_nothing_changes(self, me):
        response = me.client.patch(_PROFILE, json={"city": "Lisbon"}, headers={"If-Match": '"99"'})

        assert response.status_code == 412
        assert me.client.get(_PROFILE).json()["city"] == "Porto"

    @pytest.mark.parametrize(
        "body",
        [
            {"username": "renamed"},
            {"email": "new@example.com"},
            {"access_type": "admin"},
            {"weight_units": "stones"},
        ],
        ids=["username", "email", "access-type", "weight-unit"],
    )
    def test_what_the_profile_edit_does_not_take_is_refused(self, me, body):
        version = me.client.get(_PROFILE).json()["version"]

        response = me.client.patch(_PROFILE, json=body, headers={"If-Match": f'"{version}"'})

        assert response.status_code == 422
        assert me.client.get(_PROFILE).json()["access_type"] == "regular"


class TestPhoto:
    def test_the_first_photo_answers_201_and_a_second_replaces_it_with_200(self, me):
        first = me.client.put(f"{_PROFILE}/photo", files={"file": ("me.png", png(60, 16), "image/png")})
        second = me.client.put(f"{_PROFILE}/photo", files={"file": ("me.png", png(120, 16), "image/png")})

        assert (first.status_code, second.status_code) == (201, 200)
        assert first.json()["photo_path"] and first.json()["photo_path"] == second.json()["photo_path"]
        assert me.client.get(_PROFILE).json()["photo_path"] == second.json()["photo_path"]

    def test_a_file_that_is_not_an_image_is_refused(self, me):
        response = me.client.put(f"{_PROFILE}/photo", files={"file": ("me.png", b"not an image", "image/png")})

        assert response.status_code in (400, 415, 422)
        assert me.client.get(_PROFILE).json()["photo_path"] is None

    def test_an_extension_that_is_not_an_image_is_refused(self, me):
        response = me.client.put(f"{_PROFILE}/photo", files={"file": ("me.exe", png(), "image/png")})

        assert response.status_code == 415

    def test_deleting_the_photo_clears_it(self, me):
        me.client.put(f"{_PROFILE}/photo", files={"file": ("me.png", png(60, 16), "image/png")})

        response = me.client.delete(f"{_PROFILE}/photo")

        assert response.status_code == 204
        assert me.client.get(_PROFILE).json()["photo_path"] is None


class TestUsernameChange:
    def test_the_username_changes_after_step_up_and_the_profile_comes_back_with_its_etag(self, me):
        response = me.client.post(f"{_PROFILE}/username/change", json={"username": "Ada.Lovelace", **_STEP_UP})

        assert response.status_code == 200
        assert response.json()["username"] == "ada.lovelace"
        assert _etag(response) == f'"{response.json()["version"]}"'

    def test_a_wrong_password_is_refused_as_a_failed_step_up(self, me):
        response = me.client.post(
            f"{_PROFILE}/username/change", json={"username": "renamed", "step_up": {"current_password": "wrong"}}
        )

        assert response.status_code == 403
        assert response.json()["type"] == "urn:endurain:error:step-up-failed"
        assert me.client.get(_PROFILE).json()["username"] == "ada"

    def test_a_taken_username_is_a_conflict(self, me, committed_sessions):
        with committed_sessions() as db:
            make_user(db, username="taken")
            db.commit()

        response = me.client.post(f"{_PROFILE}/username/change", json={"username": "taken", **_STEP_UP})

        assert response.status_code == 409
        assert me.client.get(_PROFILE).json()["username"] == "ada"

    @pytest.mark.parametrize("username", ["", "has space", "bad/char"])
    def test_an_invalid_username_is_refused(self, me, username):
        response = me.client.post(f"{_PROFILE}/username/change", json={"username": username, **_STEP_UP})

        assert response.status_code == 422


class TestEmailChange:
    def test_the_change_is_pending_until_confirmed_and_the_answer_says_so(self, me, user, committed_sessions):
        with committed_sessions() as db:
            edit_mail_settings(db, host="smtp.example.com")
            db.commit()

        response = me.client.post(f"{_PROFILE}/email/change", json={"email": "New@Example.com", **_STEP_UP})

        assert response.status_code == 200
        assert response.json()["pending_email"] == "new@example.com"
        assert response.json()["email"] == user.email
        assert _etag(response) == f'"{response.json()["version"]}"'

    def test_without_mail_the_address_changes_at_once(self, me):
        response = me.client.post(f"{_PROFILE}/email/change", json={"email": "new@example.com", **_STEP_UP})

        assert response.status_code == 200
        assert (response.json()["email"], response.json()["pending_email"]) == ("new@example.com", None)

    def test_a_wrong_password_is_refused(self, me, user):
        response = me.client.post(
            f"{_PROFILE}/email/change", json={"email": "new@example.com", "step_up": {"current_password": "wrong"}}
        )

        assert response.status_code == 403
        assert me.client.get(_PROFILE).json()["email"] == user.email

    def test_the_address_must_be_valid(self, me):
        response = me.client.post(f"{_PROFILE}/email/change", json={"email": "not-an-address", **_STEP_UP})

        assert response.status_code == 422

    def test_resending_and_cancelling_answer_204_and_cancelling_clears_the_pending_change(self, me, committed_sessions):
        with committed_sessions() as db:
            edit_mail_settings(db, host="smtp.example.com")
            db.commit()
        me.client.post(f"{_PROFILE}/email/change", json={"email": "new@example.com", **_STEP_UP})

        resent = me.client.post(f"{_PROFILE}/email/change/resend")
        cancelled = me.client.delete(f"{_PROFILE}/email/change")

        assert (resent.status_code, cancelled.status_code) == (204, 204)
        assert me.client.get(_PROFILE).json()["pending_email"] is None


class TestPrivacySettings:
    def test_the_settings_are_edited_with_the_etag_they_were_read_with(self, me):
        read = me.client.get(f"{_PROFILE}/privacy")
        assert read.status_code == 200 and _etag(read) == '"1"'

        edited = me.client.patch(
            f"{_PROFILE}/privacy",
            json={"hide_activity_map": True, "default_activity_visibility": "followers"},
            headers={"If-Match": _etag(read)},
        )

        assert edited.status_code == 200
        assert _etag(edited) == '"2"'
        body = me.client.get(f"{_PROFILE}/privacy").json()
        assert (body["hide_activity_map"], body["default_activity_visibility"]) == (True, "followers")
        assert me.client.get(_PROFILE).json()["hide_activity_map"] is True

    def test_a_stale_version_is_refused_and_nothing_changes(self, me):
        response = me.client.patch(f"{_PROFILE}/privacy", json={"hide_activity_map": True}, headers={"If-Match": '"7"'})

        assert response.status_code == 412
        assert me.client.get(f"{_PROFILE}/privacy").json()["hide_activity_map"] is False

    def test_an_unknown_setting_or_visibility_is_refused(self, me):
        for body in ({"hide_everything": True}, {"default_activity_visibility": "everyone"}):
            response = me.client.patch(f"{_PROFILE}/privacy", json=body, headers={"If-Match": '"1"'})

            assert response.status_code == 422


class TestPasswordChange:
    def test_the_new_password_signs_in_and_the_old_one_does_not(self, app, me, user):
        response = me.client.post(f"{_PROFILE}/password/change", json={"password": _NEW_PASSWORD, **_STEP_UP})

        assert response.status_code == 204
        web = TestClient(app, headers={"X-Client-Type": "web"})
        assert (
            web.post(f"{_API}/auth/login", data={"username": user.username, "password": _NEW_PASSWORD}).status_code
            == 200
        )
        assert web.post(f"{_API}/auth/login", data={"username": user.username, "password": PASSWORD}).status_code == 401

    def test_a_short_password_is_the_typed_password_too_short_problem(self, me):
        response = me.client.post(f"{_PROFILE}/password/change", json={"password": "short", **_STEP_UP})

        assert response.status_code == 422
        assert response.json()["type"] == "urn:endurain:error:password-too-short"

    def test_a_wrong_current_password_is_refused(self, me):
        response = me.client.post(
            f"{_PROFILE}/password/change",
            json={"password": _NEW_PASSWORD, "step_up": {"current_password": "wrong"}},
        )

        assert response.status_code == 403
        assert response.json()["type"] == "urn:endurain:error:step-up-failed"


class TestExport:
    def test_the_export_is_queued_run_and_downloaded_by_the_session_that_asked(self, me, user, running_transfers):
        queued = me.client.post(f"{_PROFILE}/export", json=_STEP_UP)

        assert queued.status_code == 202
        job_id = queued.json()["id"]
        assert queued.headers["Content-Location"].endswith(f"/jobs/{job_id}")
        assert queued.headers["Retry-After"] == str(profile_constants.EXPORT_POLL_SECONDS)
        running_transfers()
        job = me.client.get(f"{_API}/jobs/{job_id}")
        assert job.json()["status"] == "succeeded"

        download = me.client.get(f"{_PROFILE}/export/download")

        assert download.status_code == 200
        assert download.headers["Content-Type"] == "application/zip"
        assert download.headers["Content-Disposition"] == f"attachment; filename=user_{user.id}_export.zip"
        assert "no-store" in download.headers["Cache-Control"]
        assert int(download.headers["Content-Length"]) == len(download.content)
        with zipfile.ZipFile(io.BytesIO(download.content)) as zipf:
            assert "data/user.json" in zipf.namelist()

    def test_a_wrong_password_queues_nothing(self, me, running_transfers):
        response = me.client.post(f"{_PROFILE}/export", json={"step_up": {"current_password": "wrong"}})

        assert response.status_code == 403
        assert me.client.get(f"{_PROFILE}/export/download").status_code == 404

    def test_an_export_without_a_body_is_refused(self, me):
        assert me.client.post(f"{_PROFILE}/export").status_code == 422

    def test_a_second_export_while_one_is_pending_is_a_conflict(self, me):
        first = me.client.post(f"{_PROFILE}/export", json=_STEP_UP)
        second = me.client.post(f"{_PROFILE}/export", json=_STEP_UP)

        assert (first.status_code, second.status_code) == (202, 409)

    def test_the_download_is_not_found_before_the_export_has_finished(self, me):
        me.client.post(f"{_PROFILE}/export", json=_STEP_UP)

        assert me.client.get(f"{_PROFILE}/export/download").status_code == 404

    def test_another_session_of_the_user_cannot_download_it(self, me, user, sign_in, running_transfers):
        me.client.post(f"{_PROFILE}/export", json=_STEP_UP)
        running_transfers()

        other_session = sign_in(user)

        assert other_session.client.get(f"{_PROFILE}/export/download").status_code == 404
        assert me.client.get(f"{_PROFILE}/export/download").status_code == 200


class TestImport:
    def _upload(self, client, archive, name="export.zip"):
        return client.post(f"{_PROFILE}/import", files={"file": (name, archive, "application/zip")})

    def test_the_archive_is_staged_run_and_its_rows_land_on_the_account(
        self, me, user, committed_sessions, running_transfers
    ):
        archive = profile_archive(
            user,
            user_goals=[
                {"interval": "daily", "activity_type": "run", "goal_type": "activities", "goal_activities_number": 2}
            ],
        )

        queued = self._upload(me.client, archive)

        assert queued.status_code == 202
        job_id = queued.json()["id"]
        assert queued.headers["Content-Location"].endswith(f"/jobs/{job_id}")
        running_transfers()
        job = me.client.get(f"{_API}/jobs/{job_id}").json()
        assert (job["status"], job["imported"]["user_goals"]) == ("succeeded", 1)
        with committed_sessions() as db:
            assert goals_crud.count_user_goals(user.id, db) == 1

    def test_a_second_import_while_one_is_pending_is_a_conflict(self, me, user):
        archive = profile_archive(user, user_goals=[])

        first = self._upload(me.client, archive)
        second = self._upload(me.client, archive)

        assert (first.status_code, second.status_code) == (202, 409)

    def test_an_upload_that_is_not_a_zip_is_refused_at_once_and_frees_the_user_to_retry(self, me, user):
        refused = self._upload(me.client, b"this is not an archive")

        assert refused.status_code in (400, 415, 422)
        assert self._upload(me.client, profile_archive(user, user_goals=[])).status_code == 202

    def test_an_archive_from_another_account_fails_the_job_not_the_request(
        self, me, committed_sessions, running_transfers
    ):
        with committed_sessions() as db:
            stranger = make_user(db)
            db.commit()

        queued = self._upload(me.client, profile_archive(stranger, user_goals=[]))
        running_transfers()

        assert queued.status_code == 202
        job = me.client.get(f"{_API}/jobs/{queued.json()['id']}").json()
        assert (job["status"], job["error_code"]) == ("failed", "wrong_account")


class TestDeleteAccount:
    def test_the_deletion_is_queued_the_cookie_cleared_and_the_account_signed_out(self, me, user):
        response = me.client.post(f"{_PROFILE}/delete-account", json=_STEP_UP)

        assert response.status_code == 202
        assert response.json()["kind"] == "user_deletion"
        assert me.client.get(_PROFILE).status_code == 401

    def test_a_wrong_password_deletes_nothing(self, me):
        response = me.client.post(f"{_PROFILE}/delete-account", json={"step_up": {"current_password": "wrong"}})

        assert response.status_code == 403
        assert me.client.get(_PROFILE).status_code == 200

    def test_the_only_administrator_is_refused(self, sign_in, committed_sessions):
        with committed_sessions() as db:
            admin = make_admin(db)
            db.commit()
        signed = sign_in(admin)

        response = signed.client.post(f"{_PROFILE}/delete-account", json=_STEP_UP)

        assert response.status_code == 409
        assert response.json()["type"] == "urn:endurain:error:last-administrator"
        assert signed.client.get(_PROFILE).status_code == 200
