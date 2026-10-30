"""Comprehensive tests for profile.router endpoints."""

import io
import os
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import core.config as core_config
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.auth.mfa.schema as mfa_schema
import modules.auth.sessions.schema as auth_sessions_schema
import modules.users.users.schema as users_schema
import modules.users.users_privacy_settings.schema as users_privacy_settings_schema

PREFIX = core_config.ROOT_PATH + "/profile"  # /api/v1/profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user_mock() -> users_schema.UsersRead:
    """Return the user as ``users_integration.require_user`` serves it."""
    return users_schema.UsersRead(
        id=1,
        version=1,
        name="Test User",
        username="testuser",
        email="test@example.com",
        city=None,
        birthdate=None,
        preferred_language="en",
        gender="unspecified",
        units="metric",
        height=None,
        max_heart_rate=None,
        first_day_of_week="monday",
        currency="euro",
        timezone=None,
        access_type="regular",
        photo_path=None,
        active=True,
        mfa_enabled=False,
        email_verified=True,
        pending_admin_approval=False,
        external_auth_count=0,
    )


def _make_integration_mock() -> MagicMock:
    integ = MagicMock()
    integ.version = 2
    integ.strava_token = None
    integ.garminconnect_token = None
    return integ


def _make_privacy_mock() -> MagicMock:
    p = MagicMock()
    p.version = 1
    p.default_activity_visibility = "public"
    p.hide_activity_start_time = False
    p.hide_activity_location = False
    p.hide_activity_map = False
    p.hide_activity_hr = False
    p.hide_activity_power = False
    p.hide_activity_cadence = False
    p.hide_activity_elevation = False
    p.hide_activity_speed = False
    p.hide_activity_pace = False
    p.hide_activity_laps = False
    p.hide_activity_workout_sets_steps = False
    p.hide_activity_gear = False
    return p


def _make_session_mock(session_id: str = "session-1") -> MagicMock:
    s = MagicMock()
    s.id = session_id
    s.ip_address = "127.0.0.1"
    s.device_type = "web"
    s.operating_system = "Linux"
    s.operating_system_version = "6.0"
    s.browser = "Firefox"
    s.browser_version = "120.0"
    s.created_at = datetime.now(UTC)
    s.last_activity_at = datetime.now(UTC)
    s.expires_at = datetime.now(UTC)
    s.user_id = 1
    return s


def _make_idp_mock(idp_id: int = 1) -> MagicMock:
    idp = MagicMock()
    idp.id = idp_id
    idp.name = "TestIdP"
    idp.slug = "testidp"
    idp.icon = "icon.png"
    idp.provider_type = "oauth2"
    idp.enabled = True
    return idp


# ===================================================================
# GET /profile
# ===================================================================


class TestReadUsersMe:
    """Tests for GET /profile — read_users_me."""

    @patch("modules.users.users_profile.service.users_privacy_settings_integration.get_privacy_settings")
    @patch("modules.users.users_profile.service.user_integrations_integration.get_user_integrations")
    @patch("modules.users.users_profile.service.users_integration.require_user")
    def test_the_profile_carries_the_users_version_as_its_etag(
        self, mock_get_user, mock_get_integrations, mock_get_privacy, profile_client, mock_auth_services
    ):
        mock_get_user.return_value = _make_user_mock()
        mock_get_user.return_value = mock_get_user.return_value.model_copy(update={"version": 8})
        mock_get_integrations.return_value = _make_integration_mock()
        mock_get_privacy.return_value = _make_privacy_mock()
        mock_auth_services.has_local_password.return_value = True
        mock_auth_services.get_mfa_status.return_value = mfa_schema.MFAStatusRead(mfa_enabled=False)

        response = profile_client.get(PREFIX)

        assert response.headers["ETag"] == '"8"'
        assert response.json()["integrations_version"] == 2

    @patch("modules.users.users_profile.service.users_privacy_settings_integration.get_privacy_settings")
    @patch("modules.users.users_profile.service.user_integrations_integration.get_user_integrations")
    @patch("modules.users.users_profile.service.users_integration.require_user")
    def test_success(
        self,
        mock_get_user,
        mock_get_integrations,
        mock_get_privacy,
        profile_client,
        mock_auth_services,
    ):
        """Happy path: all data found."""
        mock_get_user.return_value = _make_user_mock()
        mock_get_integrations.return_value = _make_integration_mock()
        mock_get_privacy.return_value = _make_privacy_mock()
        mock_auth_services.has_local_password.return_value = True
        mock_auth_services.get_mfa_status.return_value = mfa_schema.MFAStatusRead(mfa_enabled=True)

        response = profile_client.get(PREFIX)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "Test User"
        assert data["is_strava_linked"] == 0
        assert data["has_local_password"] is True
        assert data["mfa_enabled"] is True

    @patch("modules.users.users_profile.service.users_privacy_settings_integration.get_privacy_settings")
    @patch("modules.users.users_profile.service.user_integrations_integration.get_user_integrations")
    @patch("modules.users.users_profile.service.users_integration.require_user")
    def test_user_not_found(
        self,
        mock_get_user,
        mock_get_integrations,
        mock_get_privacy,
        profile_client,
    ):
        """Error: user not found → 404."""
        mock_get_user.side_effect = core_exceptions.NotFoundError("User not found")

        response = profile_client.get(PREFIX)

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"

    @patch("modules.users.users_profile.service.users_privacy_settings_integration.get_privacy_settings")
    @patch("modules.users.users_profile.service.user_integrations_integration.get_user_integrations")
    @patch("modules.users.users_profile.service.users_integration.require_user")
    def test_integrations_not_found(
        self,
        mock_get_user,
        mock_get_integrations,
        mock_get_privacy,
        profile_client,
    ):
        """Error: integrations not found → 404."""
        mock_get_user.return_value = _make_user_mock()
        mock_get_integrations.return_value = None

        response = profile_client.get(PREFIX)

        assert response.status_code == 404
        assert response.json()["detail"] == "User integrations not found"

    @patch("modules.users.users_profile.service.users_privacy_settings_integration.get_privacy_settings")
    @patch("modules.users.users_profile.service.user_integrations_integration.get_user_integrations")
    @patch("modules.users.users_profile.service.users_integration.require_user")
    def test_privacy_not_found(
        self,
        mock_get_user,
        mock_get_integrations,
        mock_get_privacy,
        profile_client,
    ):
        """Error: privacy settings not found → 404."""
        mock_get_user.return_value = _make_user_mock()
        mock_get_integrations.return_value = _make_integration_mock()
        mock_get_privacy.return_value = None

        response = profile_client.get(PREFIX)

        assert response.status_code == 404
        assert "privacy settings" in response.json()["detail"]


# ===================================================================
# GET /profile/sessions
# ===================================================================


class TestReadSessionsMe:
    """Tests for GET /profile/sessions — read_sessions_me."""

    def test_success(self, profile_client, mock_auth_services):
        """Happy path: returns sessions."""
        mock_auth_services.list_user_sessions.return_value = auth_sessions_schema.UsersSessionsPage.build(
            [auth_sessions_schema.UsersSessionsRead.model_validate(_make_session_mock())], 3, 2, 1
        )

        response = profile_client.get(PREFIX + "/sessions?page_number=2&num_records=1")

        assert response.status_code == 200
        data = response.json()
        assert [item["id"] for item in data["items"]] == ["session-1"]
        assert (data["total"], data["page"], data["num_records"], data["next"]) == (3, 2, 1, 3)
        assert mock_auth_services.list_user_sessions.call_args.args == (1, core_pagination.PageParams(2, 1))

    def test_rejects_an_oversized_page(self, profile_client):
        """A page size above the cap is a validation error."""
        response = profile_client.get(PREFIX + "/sessions?num_records=201")

        assert response.status_code == 422

    def test_demo_environment(self, profile_client, mock_auth_services):
        """Demo environment returns empty list."""
        mock_auth_services.list_user_sessions.return_value = auth_sessions_schema.UsersSessionsPage.build([], 0, 1, 25)

        response = profile_client.get(PREFIX + "/sessions")

        assert response.status_code == 200
        assert response.json()["items"] == []
        assert mock_auth_services.list_user_sessions.call_args.args == (1, core_pagination.PageParams(1, 25))


# ===================================================================
# POST /profile/identity-providers/{idp_id}/link/token
# ===================================================================


class TestGenerateLinkToken:
    """Tests for POST /profile/identity-providers/{idp_id}/link/token — generate_link_token."""

    def test_success(self, profile_client, mock_auth_services):
        """Happy path: generates a link token."""
        mock_auth_services.generate_link_token.return_value = {
            "token": "tok-1",
            "expires_at": datetime(2025, 1, 1, tzinfo=UTC),
        }

        response = profile_client.post(
            PREFIX + "/identity-providers/1/link/token",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 201
        assert response.json()["token"] == "tok-1"

    def test_step_up_fails(self, profile_client, mock_auth_services):
        """Error: step-up verification fails."""
        mock_auth_services.generate_link_token.side_effect = HTTPException(
            status_code=401,
            detail="Invalid credentials",
        )

        response = profile_client.post(
            PREFIX + "/identity-providers/1/link/token",
            json={"current_password": "wrong"},
        )

        assert response.status_code == 401

    def test_idp_not_found(self, profile_client, mock_auth_services):
        """Error: IDP not found → 404."""
        mock_auth_services.generate_link_token.side_effect = HTTPException(
            status_code=404,
            detail="Identity provider not found or disabled",
        )

        response = profile_client.post(
            PREFIX + "/identity-providers/1/link/token",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_idp_disabled(self, profile_client, mock_auth_services):
        """Error: IDP disabled → 404."""
        mock_auth_services.generate_link_token.side_effect = HTTPException(
            status_code=404,
            detail="Identity provider not found or disabled",
        )

        response = profile_client.post(
            PREFIX + "/identity-providers/1/link/token",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_already_linked(self, profile_client, mock_auth_services):
        """Error: already linked → 409."""
        mock_auth_services.generate_link_token.side_effect = HTTPException(
            status_code=409,
            detail="already linked",
        )

        response = profile_client.post(
            PREFIX + "/identity-providers/1/link/token",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 409
        assert "already linked" in response.json()["detail"]

    def test_idp_not_found_none_return(self, profile_client, mock_auth_services):
        """Error: IDP get returns None (second branch)."""
        mock_auth_services.generate_link_token.side_effect = HTTPException(
            status_code=404,
            detail="Identity provider not found or disabled",
        )

        response = profile_client.post(
            PREFIX + "/identity-providers/1/link/token",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 404


# ===================================================================
# POST /profile/photo
# ===================================================================


class TestUploadProfileImage:
    """Tests for POST /profile/photo — upload_profile_image."""

    @patch("modules.users.users_profile.router.users_integration.require_user")
    @patch("modules.users.users_profile.router.users_integration.upload_user_photo")
    def test_success(self, mock_save, mock_require, profile_client):
        """Happy path: the upload answers with the servable photo URL."""
        mock_save.return_value = "photo.jpg"
        mock_require.return_value = MagicMock(photo_path="/users/1/photo?t=x")

        response = profile_client.post(
            PREFIX + "/photo",
            files={"file": ("photo.jpg", b"image-data", "image/jpeg")},
        )

        assert response.status_code == 201
        assert response.json() == {"photo_path": "/users/1/photo?t=x"}


# ===================================================================
# PATCH /profile
# ===================================================================


class TestEditUser:
    """Tests for PATCH /profile — edit_user."""

    @patch("modules.users.users_profile.service.users_privacy_settings_integration.get_privacy_settings")
    @patch("modules.users.users_profile.service.user_integrations_integration.get_user_integrations")
    @patch("modules.users.users_profile.service.users_integration.require_user")
    @patch("modules.users.users_profile.service.users_integration.edit_profile")
    def test_success(
        self,
        mock_edit,
        mock_get_user,
        mock_get_integrations,
        mock_get_privacy,
        profile_client,
        mock_auth_services,
    ):
        """Happy path: the edit answers 200 with the updated profile and its new ETag."""
        updated = _make_user_mock().model_copy(update={"name": "Updated Name", "version": 3})
        mock_edit.return_value = updated
        mock_get_user.return_value = updated
        mock_get_integrations.return_value = _make_integration_mock()
        mock_get_privacy.return_value = _make_privacy_mock()
        mock_auth_services.has_local_password.return_value = True
        mock_auth_services.get_mfa_status.return_value = mfa_schema.MFAStatusRead(mfa_enabled=False)

        response = profile_client.patch(
            PREFIX,
            json={"name": "Updated Name"},
            headers={"If-Match": '"1"'},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"
        assert response.headers["ETag"] == '"3"'
        mock_edit.assert_called_once()


# ===================================================================
# PATCH /profile/privacy
# ===================================================================


class TestEditProfileEmail:
    """Tests for POST /profile/email/change — edit_profile_email."""

    @patch("modules.users.users_profile.service.users_privacy_settings_integration.get_privacy_settings")
    @patch("modules.users.users_profile.service.user_integrations_integration.get_user_integrations")
    @patch("modules.users.users_profile.service.sign_up_tokens_integration.request_email_change", return_value=True)
    @patch("modules.users.users_profile.service.users_integration.require_email_available")
    @patch("modules.users.users_profile.service.users_integration.require_user")
    def test_success_runs_the_step_up_and_answers_with_the_profile_and_its_etag(
        self,
        mock_require,
        _available,
        mock_request,
        mock_integrations,
        mock_privacy,
        profile_client,
        mock_auth_services,
    ):
        mock_require.return_value = _make_user_mock().model_copy(update={"version": 4})
        mock_integrations.return_value = _make_integration_mock()
        mock_privacy.return_value = _make_privacy_mock()
        mock_auth_services.has_local_password.return_value = True
        mock_auth_services.get_mfa_status.return_value = mfa_schema.MFAStatusRead(mfa_enabled=False)

        response = profile_client.post(
            PREFIX + "/email/change",
            json={"email": "new@example.com", "current_password": "pw", "mfa_code": None},
        )

        assert response.status_code == 200
        assert response.json()["email"] == "test@example.com"
        assert response.headers["ETag"] == '"4"'
        mock_auth_services.verify_step_up.assert_called_once()
        assert mock_request.call_args.args[:3] == (1, "new@example.com", "test@example.com")

    @patch("modules.users.users_profile.service.sign_up_tokens_integration.request_email_change")
    def test_step_up_fails(self, mock_request, profile_client, mock_auth_services):
        mock_auth_services.verify_step_up.side_effect = HTTPException(status_code=401, detail="Invalid credentials")

        response = profile_client.post(
            PREFIX + "/email/change",
            json={"email": "new@example.com", "current_password": "wrong"},
        )

        assert response.status_code == 401
        mock_request.assert_not_called()

    @patch("modules.users.users_profile.service.sign_up_tokens_integration.request_email_change")
    @patch(
        "modules.users.users_profile.service.users_integration.require_email_available",
        side_effect=core_exceptions.ConflictError("taken"),
    )
    @patch("modules.users.users_profile.service.users_integration.require_user")
    def test_an_address_of_another_account_is_a_conflict(self, mock_require, _available, mock_request, profile_client):
        mock_require.return_value = _make_user_mock()

        response = profile_client.post(
            PREFIX + "/email/change", json={"email": "taken@example.com", "current_password": "pw"}
        )

        assert response.status_code == 409
        mock_request.assert_not_called()

    def test_the_address_must_be_valid(self, profile_client):
        response = profile_client.post(
            PREFIX + "/email/change", json={"email": "not-an-email", "current_password": "pw"}
        )

        assert response.status_code == 422

    def test_the_plain_profile_edit_refuses_an_email(self, profile_client):
        response = profile_client.patch(PREFIX, json={"email": "new@example.com"}, headers={"If-Match": '"1"'})

        assert response.status_code == 422


class TestResendProfileEmailChange:
    """Tests for POST /profile/email/change/resend — resend_profile_email_change."""

    @patch("modules.users.users_profile.service.sign_up_tokens_integration.request_email_change_resend")
    def test_answers_204_and_asks_for_a_resend(self, mock_resend, profile_client, local_mock_db):
        response = profile_client.post(PREFIX + "/email/change/resend")

        assert response.status_code == 204
        assert mock_resend.call_args.args[0] == 1
        local_mock_db.commit.assert_called_once()


class TestCancelProfileEmailChange:
    """Tests for DELETE /profile/email/change — cancel_profile_email_change."""

    @patch("modules.users.users_profile.service.sign_up_tokens_integration.revoke_pending_tokens")
    def test_answers_204_and_revokes_the_pending_tokens(self, mock_revoke, profile_client, local_mock_db):
        response = profile_client.delete(PREFIX + "/email/change")

        assert response.status_code == 204
        mock_revoke.assert_called_once_with(1, local_mock_db)
        local_mock_db.commit.assert_called_once()


class TestEditProfilePrivacySettings:
    """Tests for PATCH /profile/privacy — edit_profile_privacy_settings."""

    @patch("modules.users.users_profile.service.users_privacy_settings_integration.edit_privacy_settings")
    def test_success(self, mock_edit, profile_client):
        """Happy path: update privacy settings, answering with the version the edit produced."""
        mock_edit.return_value = users_privacy_settings_schema.UsersPrivacySettingsRead(
            id=1,
            user_id=1,
            version=5,
            default_activity_visibility=users_privacy_settings_schema.ActivityVisibility.FOLLOWERS,
        )
        response = profile_client.patch(
            PREFIX + "/privacy",
            json={"default_activity_visibility": "followers"},
            headers={"If-Match": '"1"'},
        )

        assert response.status_code == 200
        assert response.json()["default_activity_visibility"] == "followers"
        assert response.headers["ETag"] == '"5"'


# ===================================================================
# POST /profile/password/change
# ===================================================================


class TestEditProfilePassword:
    """Tests for POST /profile/password/change — edit_profile_password."""

    def test_success(
        self,
        profile_client,
        mock_auth_services,
    ):
        """Happy path: update password."""
        response = profile_client.post(
            PREFIX + "/password/change",
            json={
                "current_password": "oldpass",
                "password": "NewPass123!",
                "mfa_code": None,
            },
        )

        assert response.status_code == 204
        mock_auth_services.change_own_password.assert_called_once()

    def test_step_up_fails(
        self,
        profile_client,
        mock_auth_services,
    ):
        """Error: step-up verification fails."""
        mock_auth_services.change_own_password.side_effect = HTTPException(
            status_code=401,
            detail="Invalid credentials",
        )

        response = profile_client.post(
            PREFIX + "/password/change",
            json={
                "current_password": "wrong",
                "password": "NewPass123!",
                "mfa_code": None,
            },
        )

        assert response.status_code == 401


# ===================================================================
# DELETE /profile/photo
# ===================================================================


class TestDeleteProfilePhoto:
    """Tests for DELETE /profile/photo — delete_profile_photo."""

    @patch("modules.users.users_profile.router.users_integration.delete_user_photo")
    def test_success(self, mock_update, profile_client):
        """Happy path: delete profile photo."""
        response = profile_client.delete(PREFIX + "/photo")

        assert response.status_code == 204
        mock_update.assert_called_once()


# ===================================================================
# DELETE /profile/sessions/{session_id}
# ===================================================================


class TestDeleteProfileSession:
    """Tests for DELETE /profile/sessions/{session_id} — delete_profile_session."""

    def test_success(self, profile_client):
        """Happy path: delete session."""
        response = profile_client.delete(PREFIX + "/sessions/session-1")

        assert response.status_code == 204


# ===================================================================
# DELETE /profile/sessions
# ===================================================================


class TestDeleteProfileOtherSessions:
    """Tests for DELETE /profile/sessions — delete_profile_other_sessions."""

    def test_success(self, profile_client, mock_auth_services):
        """Happy path: revokes other sessions, keeping the caller's current one."""
        response = profile_client.delete(PREFIX + "/sessions")

        assert response.status_code == 204
        mock_auth_services.delete_other_user_sessions.assert_called_once_with(1, "session-1")


# ===================================================================
# POST /profile/export, GET /profile/export, GET /profile/export/download
# ===================================================================


class TestExportProfileData:
    """Tests for POST /profile/export — export_profile_data."""

    _PUBLISH = "modules.users.users_profile.export_job_service.profile_event_publishers.publish_export_requested"

    def test_queues_the_export_and_answers_at_once(self, profile_client, export_states):
        with patch(self._PUBLISH) as publish:
            response = profile_client.post(PREFIX + "/export")

        assert response.status_code == 202
        assert response.json() == {"status": "queued", "failure": None, "size_bytes": None}
        assert publish.call_args.args[0] == 1
        assert export_states.get(1).status == "queued"

    def test_a_second_export_while_one_is_pending_is_a_conflict(self, profile_client):
        with patch(self._PUBLISH):
            first = profile_client.post(PREFIX + "/export")
            second = profile_client.post(PREFIX + "/export")

        assert (first.status_code, second.status_code) == (202, 409)


class TestReadProfileExportStatus:
    """Tests for GET /profile/export — read_profile_export_status."""

    def test_reports_the_recorded_state(self, profile_client, export_states):
        export_states.begin(1)
        export_states.set_status(1, "completed", size_bytes=9)

        response = profile_client.get(PREFIX + "/export")

        assert response.status_code == 200
        assert response.json() == {"status": "completed", "failure": None, "size_bytes": 9}

    def test_is_not_found_when_nothing_was_exported(self, profile_client):
        assert profile_client.get(PREFIX + "/export").status_code == 404

    def test_one_user_cannot_read_another_users_export(self, profile_client, export_states):
        export_states.begin(2)

        assert profile_client.get(PREFIX + "/export").status_code == 404


class TestDownloadProfileExport:
    """Tests for GET /profile/export/download — download_profile_export."""

    def test_streams_the_finished_archive(self, profile_app, profile_client, export_states):
        export_states.begin(1)
        export_states.set_status(1, "completed", size_bytes=8)
        storage = MagicMock()
        storage.open_stream.return_value = io.BytesIO(b"zip-data")
        profile_app.dependency_overrides[core_dependencies.get_storage] = lambda: storage

        response = profile_client.get(PREFIX + "/export/download")

        assert response.status_code == 200
        assert response.content == b"zip-data"
        assert response.headers["content-length"] == "8"
        storage.open_stream.assert_called_once_with("profile_export_staging", "1.zip")

    def test_is_not_found_before_the_export_has_finished(self, profile_client, export_states):
        export_states.begin(1)

        assert profile_client.get(PREFIX + "/export/download").status_code == 404


# ===================================================================
# POST /profile/import
# ===================================================================


def _write_upload(_file, *, kind, upload_dir, filename):
    """Stand in for the shared validator: write the archive where it would."""
    path = os.path.join(upload_dir, filename)
    with open(path, "wb") as out:
        out.write(b"zip-data")
    return path


class TestImportProfileData:
    """Tests for POST /profile/import — import_profile_data."""

    _PUBLISH = "modules.users.users_profile.import_job_service.profile_event_publishers.publish_import_requested"

    @patch("modules.users.users_profile.router.core_file_uploads.save_validated_upload_sync", side_effect=_write_upload)
    def test_accepts_the_archive_and_queues_it(self, mock_validate, profile_client, import_states):
        with patch(self._PUBLISH) as publish:
            response = profile_client.post(
                PREFIX + "/import",
                files={"file": ("test.zip", b"zip-data", "application/zip")},
            )

        assert response.status_code == 202
        assert response.json() == {"status": "queued", "failure": None, "imported": None}
        publish.assert_called_once()
        assert publish.call_args.args[0] == 1
        assert publish.call_args.args[1].startswith("1/")
        assert import_states.get(1).status == "queued"

    @patch("modules.users.users_profile.router.core_file_uploads.save_validated_upload_sync", side_effect=_write_upload)
    def test_a_second_import_while_one_is_pending_is_a_conflict(self, mock_validate, profile_client):
        files = {"file": ("test.zip", b"zip-data", "application/zip")}

        with patch(self._PUBLISH) as publish:
            first = profile_client.post(PREFIX + "/import", files=files)
            second = profile_client.post(PREFIX + "/import", files=files)

        assert (first.status_code, second.status_code) == (202, 409)
        publish.assert_called_once()

    @patch("modules.users.users_profile.router.core_file_uploads.save_validated_upload_sync", side_effect=_write_upload)
    def test_a_queueing_failure_frees_the_user_to_retry(self, mock_validate, profile_client, import_states):
        files = {"file": ("test.zip", b"zip-data", "application/zip")}

        with patch(self._PUBLISH, side_effect=RuntimeError("outbox down")), pytest.raises(RuntimeError):
            profile_client.post(PREFIX + "/import", files=files)

        assert import_states.get(1).status == "failed"
        with patch(self._PUBLISH):
            assert profile_client.post(PREFIX + "/import", files=files).status_code == 202


class TestReadProfileImportStatus:
    """Tests for GET /profile/import — read_profile_import_status."""

    def test_reports_the_recorded_state(self, profile_client, import_states):
        import_states.begin(1)
        import_states.set_status(1, "completed", imported={"activities": 5})

        response = profile_client.get(PREFIX + "/import")

        assert response.status_code == 200
        assert response.json() == {"status": "completed", "failure": None, "imported": {"activities": 5}}

    def test_is_not_found_when_nothing_was_imported(self, profile_client):
        assert profile_client.get(PREFIX + "/import").status_code == 404

    def test_one_user_cannot_read_another_users_import(self, profile_client, import_states):
        import_states.begin(2)

        assert profile_client.get(PREFIX + "/import").status_code == 404


# ===================================================================
# GET /profile/mfa/status
# ===================================================================


class TestGetMFAStatus:
    """Tests for GET /profile/mfa/status — get_mfa_status."""

    def test_enabled(self, profile_client, mock_auth_services):
        """Returns enabled=True."""
        mock_auth_services.get_mfa_status.return_value = {"mfa_enabled": True}

        response = profile_client.get(PREFIX + "/mfa/status")

        assert response.status_code == 200
        assert response.json()["mfa_enabled"] is True

    def test_disabled(self, profile_client, mock_auth_services):
        """Returns enabled=False."""
        mock_auth_services.get_mfa_status.return_value = {"mfa_enabled": False}

        response = profile_client.get(PREFIX + "/mfa/status")

        assert response.status_code == 200
        assert response.json()["mfa_enabled"] is False


# ===================================================================
# GET /profile/mfa/backup-codes/status
# ===================================================================


class TestGetBackupCodeStatus:
    """Tests for GET /profile/mfa/backup-codes/status — get_backup_code_status."""

    def test_no_codes(self, profile_client, mock_auth_services):
        """No backup codes → has_codes=False."""
        mock_auth_services.get_backup_code_status.return_value = {
            "has_codes": False,
            "total": 0,
            "unused": 0,
            "used": 0,
            "created_at": None,
        }

        response = profile_client.get(PREFIX + "/mfa/backup-codes/status")

        assert response.status_code == 200
        data = response.json()
        assert data["has_codes"] is False
        assert data["total"] == 0

    def test_has_codes(self, profile_client, mock_auth_services):
        """Has backup codes with usage counts."""
        mock_auth_services.get_backup_code_status.return_value = {
            "has_codes": True,
            "total": 2,
            "unused": 1,
            "used": 1,
            "created_at": datetime(2025, 1, 1, tzinfo=UTC),
        }

        response = profile_client.get(PREFIX + "/mfa/backup-codes/status")

        assert response.status_code == 200
        data = response.json()
        assert data["has_codes"] is True
        assert data["total"] == 2
        assert data["unused"] == 1
        assert data["used"] == 1


# ===================================================================
# POST /profile/mfa/setup
# ===================================================================


class TestSetupMFA:
    """Tests for POST /profile/mfa/setup — setup_mfa."""

    def test_success(self, profile_client, fake_mfa_secret_store, mock_auth_services):
        """Happy path: create MFA setup."""
        mock_auth_services.setup_mfa.return_value = mfa_schema.MFASetupRead(
            secret="SECRETKEY",
            qr_code="base64qr",
            app_name="Endurain",
        )

        response = profile_client.post(PREFIX + "/mfa/setup")

        assert response.status_code == 201
        data = response.json()
        assert data["secret"] == "SECRETKEY"
        assert data["qr_code"] == "base64qr"

    def test_store_unavailable(self, profile_client, fake_mfa_secret_store, mock_auth_services):
        """MFA secret store unavailable → 503."""
        from modules.auth.mfa.setup_store import MFASecretStoreUnavailableError

        mock_auth_services.setup_mfa.side_effect = MFASecretStoreUnavailableError("MFA secret storage is unavailable")

        response = profile_client.post(PREFIX + "/mfa/setup")

        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"]


# ===================================================================
# PUT /profile/mfa/enable
# ===================================================================


class TestEnableMFA:
    """Tests for PUT /profile/mfa/enable — enable_mfa."""

    def test_success(self, profile_client, mock_auth_services):
        """Happy path: enable MFA."""
        mock_auth_services.enable_mfa.return_value = {
            "message": "MFA enabled successfully",
            "backup_codes": ["code1", "code2"],
        }

        response = profile_client.post(
            PREFIX + "/mfa/enable",
            json={"mfa_code": "123456", "current_password": "pass123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "MFA enabled successfully"
        assert data["backup_codes"] == ["code1", "code2"]

    def test_step_up_fails(self, profile_client, mock_auth_services):
        """Step-up fails before enabling."""
        mock_auth_services.enable_mfa.side_effect = HTTPException(status_code=401, detail="Invalid")

        response = profile_client.post(
            PREFIX + "/mfa/enable",
            json={"mfa_code": "123456", "current_password": "wrong"},
        )

        assert response.status_code == 401

    def test_no_setup_in_progress(self, profile_client, mock_auth_services):
        """No setup in progress → 400."""
        mock_auth_services.enable_mfa.side_effect = HTTPException(
            status_code=400,
            detail="No MFA setup in progress. Please run setup first.",
        )

        response = profile_client.post(
            PREFIX + "/mfa/enable",
            json={"mfa_code": "123456", "current_password": "pass123"},
        )

        assert response.status_code == 400
        assert "No MFA setup in progress" in response.json()["detail"]

    def test_get_secret_store_unavailable(self, profile_client, mock_auth_services):
        """get_secret raises MFASecretStoreUnavailableError → 503."""
        from modules.auth.mfa.setup_store import MFASecretStoreUnavailableError

        mock_auth_services.enable_mfa.side_effect = MFASecretStoreUnavailableError("MFA secret storage is unavailable")

        response = profile_client.post(
            PREFIX + "/mfa/enable",
            json={"mfa_code": "123456", "current_password": "pass123"},
        )

        assert response.status_code == 503

    def test_invalid_mfa_code(self, profile_client, mock_auth_services):
        """Invalid MFA code → 400."""
        mock_auth_services.enable_mfa.side_effect = HTTPException(
            status_code=400,
            detail="Invalid MFA code",
        )

        response = profile_client.post(
            PREFIX + "/mfa/enable",
            json={"mfa_code": "000000", "current_password": "pass123"},
        )

        assert response.status_code == 400

    def test_other_http_exception(self, profile_client, mock_auth_services):
        """Other HTTPException (not wrong code) → re-raised."""
        mock_auth_services.enable_mfa.side_effect = HTTPException(
            status_code=409,
            detail="MFA already enabled",
        )

        response = profile_client.post(
            PREFIX + "/mfa/enable",
            json={"mfa_code": "123456", "current_password": "pass123"},
        )

        assert response.status_code == 409


# ===================================================================
# PUT /profile/mfa/disable
# ===================================================================


class TestDisableMFA:
    """Tests for PUT /profile/mfa/disable — disable_mfa."""

    def test_success(self, profile_client, mock_auth_services):
        """Happy path: disable MFA."""
        mock_auth_services.disable_mfa.return_value = {"message": "MFA disabled successfully"}

        response = profile_client.post(
            PREFIX + "/mfa/disable",
            json={"mfa_code": "123456", "current_password": "pass123"},
        )

        assert response.status_code == 200
        assert response.json()["message"] == "MFA disabled successfully"

    def test_step_up_fails(self, profile_client, mock_auth_services):
        """Step-up fails before disable."""
        mock_auth_services.disable_mfa.side_effect = HTTPException(status_code=401, detail="Invalid")

        response = profile_client.post(
            PREFIX + "/mfa/disable",
            json={"mfa_code": "000000", "current_password": "wrong"},
        )

        assert response.status_code == 401


# ===================================================================
# POST /profile/mfa/verify
# ===================================================================


class TestVerifyMFA:
    """Tests for POST /profile/mfa/verify — verify_mfa."""

    def test_valid_code(self, profile_client, mock_auth_services):
        """Valid MFA code → success."""
        mock_auth_services.verify_mfa.return_value = {"message": "MFA code verified successfully"}

        response = profile_client.post(
            PREFIX + "/mfa/verify",
            json={"mfa_code": "123456"},
        )

        assert response.status_code == 200
        assert response.json()["message"] == "MFA code verified successfully"

    def test_invalid_code(self, profile_client, mock_auth_services):
        """Invalid MFA code → 400."""
        mock_auth_services.verify_mfa.side_effect = HTTPException(status_code=400, detail="Invalid MFA code")

        response = profile_client.post(
            PREFIX + "/mfa/verify",
            json={"mfa_code": "000000"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid MFA code"


# ===================================================================
# POST /profile/mfa/backup-codes
# ===================================================================


class TestGenerateMFABackupCodes:
    """Tests for POST /profile/mfa/backup-codes — generate_mfa_backup_codes."""

    def test_success(self, profile_client, mock_auth_services):
        """Happy path: generate backup codes."""
        mock_auth_services.generate_backup_codes.return_value = {
            "codes": ["code1", "code2"],
            "created_at": datetime(2025, 1, 1, tzinfo=UTC),
        }

        response = profile_client.post(
            PREFIX + "/mfa/backup-codes",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["codes"] == ["code1", "code2"]
        assert "created_at" in data

    def test_user_not_found(self, profile_client, mock_auth_services):
        """User not found → 404."""
        mock_auth_services.generate_backup_codes.side_effect = HTTPException(status_code=404, detail="User not found")

        response = profile_client.post(
            PREFIX + "/mfa/backup-codes",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 404

    def test_mfa_not_enabled(self, profile_client, mock_auth_services):
        """MFA not enabled → 400."""
        mock_auth_services.generate_backup_codes.side_effect = HTTPException(
            status_code=400,
            detail="MFA must be enabled to generate backup codes",
        )

        response = profile_client.post(
            PREFIX + "/mfa/backup-codes",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 400
        assert "MFA must be enabled" in response.json()["detail"]

    def test_step_up_fails(self, profile_client, mock_auth_services):
        """Step-up fails → 401."""
        mock_auth_services.generate_backup_codes.side_effect = HTTPException(status_code=401, detail="Invalid")

        response = profile_client.post(
            PREFIX + "/mfa/backup-codes",
            json={"current_password": "wrong"},
        )

        assert response.status_code == 401


# ===================================================================
# GET /profile/identity-providers
# ===================================================================


class TestGetMyIdentityProviders:
    """Tests for GET /profile/identity-providers — get_my_identity_providers."""

    def test_success(
        self,
        profile_client,
        mock_auth_services,
    ):
        """Happy path: returns enriched IdP links."""
        mock_auth_services.get_user_identity_provider_links.return_value = [
            {
                "id": 1,
                "user_id": 1,
                "idp_id": 1,
                "idp_subject": "sub",
                "linked_at": "2025-01-01T00:00:00",
                "last_login": None,
                "idp_access_token_expires_at": None,
                "idp_refresh_token_updated_at": None,
                "idp_name": "TestIdP",
                "idp_slug": "testidp",
                "idp_icon": "icon.png",
                "idp_provider_type": "oauth2",
            }
        ]

        response = profile_client.get(PREFIX + "/identity-providers")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["idp_name"] == "TestIdP"

    def test_no_links(
        self,
        profile_client,
        mock_auth_services,
    ):
        """No IdP links → empty list."""
        mock_auth_services.get_user_identity_provider_links.return_value = []

        response = profile_client.get(PREFIX + "/identity-providers")

        assert response.status_code == 200
        assert response.json() == []


# ===================================================================
# POST /profile/identity-providers/{idp_id}/unlink
# ===================================================================


class TestDeleteMyIdentityProvider:
    """Tests for POST /profile/identity-providers/{idp_id}/unlink — delete_my_identity_provider."""

    def test_success(self, profile_client, mock_auth_services):
        """Happy path: unlink IdP."""
        response = profile_client.post(
            PREFIX + "/identity-providers/1/unlink",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 204
        mock_auth_services.delete_identity_provider_link.assert_called_once()

    def test_step_up_fails(self, profile_client, mock_auth_services):
        """Step-up fails → 401."""
        mock_auth_services.delete_identity_provider_link.side_effect = HTTPException(status_code=401, detail="Invalid")

        response = profile_client.post(
            PREFIX + "/identity-providers/1/unlink",
            json={"current_password": "wrong"},
        )

        assert response.status_code == 401

    def test_idp_not_found(self, profile_client, mock_auth_services):
        """IDP not found → 404."""
        mock_auth_services.delete_identity_provider_link.side_effect = HTTPException(
            status_code=404, detail="Identity provider not found"
        )

        response = profile_client.post(
            PREFIX + "/identity-providers/1/unlink",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 404

    def test_link_not_found(self, profile_client, mock_auth_services):
        """Link not found for user → 404."""
        mock_auth_services.delete_identity_provider_link.side_effect = HTTPException(
            status_code=404, detail="Identity provider link missing"
        )

        response = profile_client.post(
            PREFIX + "/identity-providers/1/unlink",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 404

    def test_account_lockout(self, profile_client, mock_auth_services):
        """Unlinking last auth method → 400."""
        mock_auth_services.delete_identity_provider_link.side_effect = HTTPException(
            status_code=400,
            detail="Cannot unlink last authentication method. Please set a password first.",
        )

        response = profile_client.post(
            PREFIX + "/identity-providers/1/unlink",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 400
        assert "Cannot unlink" in response.json()["detail"]

    def test_deletion_fails(self, profile_client, mock_auth_services):
        """Deletion returns False → 500."""
        mock_auth_services.delete_identity_provider_link.side_effect = HTTPException(
            status_code=500, detail="Failed to unlink identity provider"
        )

        response = profile_client.post(
            PREFIX + "/identity-providers/1/unlink",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 500
        assert "Failed to unlink" in response.json()["detail"]


# ===================================================================
# POST /profile/delete-account
# ===================================================================


class TestDeleteMyAccount:
    """Tests for POST /profile/delete-account — delete_my_account."""

    @patch("modules.users.users_profile.router.profile_service.delete_account")
    @patch("modules.users.users_profile.router.authentication_dependencies.clear_refresh_token_cookies")
    def test_success(self, mock_clear_cookies, mock_delete, profile_client, mock_auth_services):
        mock_delete.return_value = users_schema.UserDeletionStatus(status="queued")
        response = profile_client.post(
            PREFIX + "/delete-account",
            json={"current_password": "secret-password", "mfa_code": "123456"},
        )

        assert response.status_code == 202
        assert response.json() == {"status": "queued"}
        assert mock_delete.call_args.args[0] == 1
        assert mock_delete.call_args.args[1] == "session-1"
        assert mock_delete.call_args.args[2].current_password == "secret-password"
        mock_clear_cookies.assert_called_once()

    @patch("modules.users.users_profile.router.profile_service.delete_account")
    def test_the_only_administrator_is_refused(self, mock_delete, profile_client, mock_auth_services):
        mock_delete.side_effect = core_exceptions.ConflictError("The only administrator cannot be deleted")

        response = profile_client.post(PREFIX + "/delete-account", json={"current_password": "secret-password"})

        assert response.status_code == 409

    @patch("modules.users.users_profile.router.profile_service.delete_account")
    def test_step_up_failure_is_returned(self, mock_delete, profile_client):
        mock_delete.side_effect = HTTPException(status_code=401, detail="Invalid credentials")

        response = profile_client.post(PREFIX + "/delete-account", json={"current_password": "wrong"})

        assert response.status_code == 401


class TestProfileEditsNeedIfMatch:
    """The profile and privacy edits are conditional on the version the client read."""

    @pytest.mark.parametrize("path", ["", "/privacy"])
    def test_an_edit_without_if_match_is_428(self, path, profile_client):
        response = profile_client.patch(PREFIX + path, json={})

        assert response.status_code == 428
