"""Comprehensive tests for profile.router endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import core.config as core_config
import modules.auth.mfa.schema as mfa_schema
import modules.users.users_profile.exceptions as profile_exceptions

PREFIX = core_config.ROOT_PATH + "/profile"  # /api/v1/profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user_mock() -> MagicMock:
    user = MagicMock()
    user.id = 1
    user.name = "Test User"
    user.username = "testuser"
    user.email = "test@example.com"
    user.city = None
    user.birthdate = None
    user.preferred_language = "en"
    user.gender = "unspecified"
    user.units = "metric"
    user.height = None
    user.max_heart_rate = None
    user.first_day_of_week = "monday"
    user.currency = "euro"
    user.timezone = None
    user.access_type = "regular"
    user.photo_path = None
    user.active = True
    user.mfa_enabled = False
    user.email_verified = True
    user.pending_admin_approval = False
    user.external_auth_count = 0
    user.is_strava_linked = 0
    user.is_garminconnect_linked = 0
    user.default_activity_visibility = "public"
    user.hide_activity_start_time = False
    user.hide_activity_location = False
    user.hide_activity_map = False
    user.hide_activity_hr = False
    user.hide_activity_power = False
    user.hide_activity_cadence = False
    user.hide_activity_elevation = False
    user.hide_activity_speed = False
    user.hide_activity_pace = False
    user.hide_activity_laps = False
    user.hide_activity_workout_sets_steps = False
    user.hide_activity_gear = False
    # Mirror the ORM: no has_local_password attribute, so
    # UsersMe.model_validate falls back to the default (None)
    # before the router overrides it via IdentityService.
    user.has_local_password = None
    return user


def _make_integration_mock() -> MagicMock:
    integ = MagicMock()
    integ.strava_token = None
    integ.garminconnect_token = None
    return integ


def _make_privacy_mock() -> MagicMock:
    p = MagicMock()
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

    @patch("modules.users.users_profile.router.users_privacy_settings_crud.get_user_privacy_settings_by_user_id")
    @patch("modules.users.users_profile.router.user_integrations_crud.get_user_integrations_by_user_id")
    @patch("modules.users.users_profile.router.users_crud.get_user_by_id")
    def test_success(
        self,
        mock_get_user,
        mock_get_integrations,
        mock_get_privacy,
        profile_client,
        mock_identity_service,
    ):
        """Happy path: all data found."""
        mock_get_user.return_value = _make_user_mock()
        mock_get_integrations.return_value = _make_integration_mock()
        mock_get_privacy.return_value = _make_privacy_mock()
        mock_identity_service.has_local_password.return_value = True
        mock_identity_service.get_mfa_status.return_value = mfa_schema.MFAStatusResponse(mfa_enabled=True)

        response = profile_client.get(PREFIX)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "Test User"
        assert data["is_strava_linked"] == 0
        assert data["has_local_password"] is True
        assert data["mfa_enabled"] is True

    @patch("modules.users.users_profile.router.users_privacy_settings_crud.get_user_privacy_settings_by_user_id")
    @patch("modules.users.users_profile.router.user_integrations_crud.get_user_integrations_by_user_id")
    @patch("modules.users.users_profile.router.users_crud.get_user_by_id")
    def test_user_not_found(
        self,
        mock_get_user,
        mock_get_integrations,
        mock_get_privacy,
        profile_client,
    ):
        """Error: user not found → 404."""
        mock_get_user.return_value = None

        response = profile_client.get(PREFIX)

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"

    @patch("modules.users.users_profile.router.users_privacy_settings_crud.get_user_privacy_settings_by_user_id")
    @patch("modules.users.users_profile.router.user_integrations_crud.get_user_integrations_by_user_id")
    @patch("modules.users.users_profile.router.users_crud.get_user_by_id")
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
        assert response.json()["detail"] == "Could not validate credentials (user integrations not found)"

    @patch("modules.users.users_profile.router.users_privacy_settings_crud.get_user_privacy_settings_by_user_id")
    @patch("modules.users.users_profile.router.user_integrations_crud.get_user_integrations_by_user_id")
    @patch("modules.users.users_profile.router.users_crud.get_user_by_id")
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

    def test_success(self, profile_client, mock_identity_service):
        """Happy path: returns sessions."""
        mock_identity_service.get_user_sessions.return_value = [_make_session_mock()]

        response = profile_client.get(PREFIX + "/sessions")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "session-1"

    def test_demo_environment(self, profile_client, mock_identity_service):
        """Demo environment returns empty list."""
        mock_identity_service.get_user_sessions.return_value = []

        response = profile_client.get(PREFIX + "/sessions")

        assert response.status_code == 200
        assert response.json() == []


# ===================================================================
# POST /profile/idp/{idp_id}/link/token
# ===================================================================


class TestGenerateLinkToken:
    """Tests for POST /profile/idp/{idp_id}/link/token — generate_link_token."""

    def test_success(self, profile_client, mock_identity_service):
        """Happy path: generates a link token."""
        mock_identity_service.generate_link_token.return_value = {
            "token": "tok-1",
            "expires_at": datetime(2025, 1, 1, tzinfo=UTC),
        }

        response = profile_client.post(
            PREFIX + "/idp/1/link/token",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 201
        assert response.json()["token"] == "tok-1"

    def test_step_up_fails(self, profile_client, mock_identity_service):
        """Error: step-up verification fails."""
        mock_identity_service.generate_link_token.side_effect = HTTPException(
            status_code=401,
            detail="Invalid credentials",
        )

        response = profile_client.post(
            PREFIX + "/idp/1/link/token",
            json={"current_password": "wrong"},
        )

        assert response.status_code == 401

    def test_idp_not_found(self, profile_client, mock_identity_service):
        """Error: IDP not found → 404."""
        mock_identity_service.generate_link_token.side_effect = HTTPException(
            status_code=404,
            detail="Identity provider not found or disabled",
        )

        response = profile_client.post(
            PREFIX + "/idp/1/link/token",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_idp_disabled(self, profile_client, mock_identity_service):
        """Error: IDP disabled → 404."""
        mock_identity_service.generate_link_token.side_effect = HTTPException(
            status_code=404,
            detail="Identity provider not found or disabled",
        )

        response = profile_client.post(
            PREFIX + "/idp/1/link/token",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_already_linked(self, profile_client, mock_identity_service):
        """Error: already linked → 409."""
        mock_identity_service.generate_link_token.side_effect = HTTPException(
            status_code=409,
            detail="already linked",
        )

        response = profile_client.post(
            PREFIX + "/idp/1/link/token",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 409
        assert "already linked" in response.json()["detail"]

    def test_idp_not_found_none_return(self, profile_client, mock_identity_service):
        """Error: IDP get returns None (second branch)."""
        mock_identity_service.generate_link_token.side_effect = HTTPException(
            status_code=404,
            detail="Identity provider not found or disabled",
        )

        response = profile_client.post(
            PREFIX + "/idp/1/link/token",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 404


# ===================================================================
# POST /profile/image
# ===================================================================


class TestUploadProfileImage:
    """Tests for POST /profile/image — upload_profile_image."""

    @patch("modules.users.users_profile.router.users_utils.save_user_image_file", new_callable=AsyncMock)
    def test_success(self, mock_save, profile_client):
        """Happy path: upload profile image."""
        mock_save.return_value = "photo.jpg"

        response = profile_client.post(
            PREFIX + "/image",
            files={"file": ("photo.jpg", b"image-data", "image/jpeg")},
        )

        assert response.status_code == 201
        assert response.json() == "photo.jpg"


# ===================================================================
# PUT /profile
# ===================================================================


class TestEditUser:
    """Tests for PUT /profile — edit_user."""

    @patch("modules.users.users_profile.router.users_crud.edit_profile_user", new_callable=AsyncMock)
    def test_success(self, mock_edit, profile_client):
        """Happy path: update profile."""
        response = profile_client.put(
            PREFIX,
            json={"name": "Updated Name"},
        )

        assert response.status_code == 200
        assert "updated successfully" in response.json()["message"]


# ===================================================================
# PUT /profile/privacy
# ===================================================================


class TestEditProfilePrivacySettings:
    """Tests for PUT /profile/privacy — edit_profile_privacy_settings."""

    @patch("modules.users.users_profile.router.users_privacy_settings_crud.edit_user_privacy_settings")
    def test_success(self, mock_edit, profile_client):
        """Happy path: update privacy settings."""
        response = profile_client.put(
            PREFIX + "/privacy",
            json={"default_activity_visibility": "followers"},
        )

        assert response.status_code == 200
        assert "privacy settings updated" in response.json()["message"]


# ===================================================================
# PUT /profile/password
# ===================================================================


class TestEditProfilePassword:
    """Tests for PUT /profile/password — edit_profile_password."""

    def test_success(
        self,
        profile_client,
        mock_identity_service,
    ):
        """Happy path: update password."""
        response = profile_client.put(
            PREFIX + "/password",
            json={
                "current_password": "oldpass",
                "password": "NewPass123!",
                "mfa_code": None,
            },
        )

        assert response.status_code == 200
        assert "password updated successfully" in response.json()["message"]
        mock_identity_service.change_own_password.assert_called_once()

    def test_step_up_fails(
        self,
        profile_client,
        mock_identity_service,
    ):
        """Error: step-up verification fails."""
        mock_identity_service.change_own_password.side_effect = HTTPException(
            status_code=401,
            detail="Invalid credentials",
        )

        response = profile_client.put(
            PREFIX + "/password",
            json={
                "current_password": "wrong",
                "password": "NewPass123!",
                "mfa_code": None,
            },
        )

        assert response.status_code == 401


# ===================================================================
# PUT /profile/photo
# ===================================================================


class TestDeleteProfilePhoto:
    """Tests for PUT /profile/photo — delete_profile_photo."""

    @patch("modules.users.users_profile.router.users_crud.update_user_photo", new_callable=AsyncMock)
    def test_success(self, mock_update, profile_client):
        """Happy path: delete profile photo."""
        mock_update.return_value = None

        response = profile_client.put(PREFIX + "/photo")

        assert response.status_code == 204


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

    def test_success(self, profile_client, mock_identity_service):
        """Happy path: revokes other sessions, keeping the caller's current one."""
        response = profile_client.delete(PREFIX + "/sessions")

        assert response.status_code == 204
        mock_identity_service.delete_other_user_sessions.assert_called_once_with(1, "session-1")


# ===================================================================
# GET /profile/export
# ===================================================================


class TestExportProfileData:
    """Tests for GET /profile/export — export_profile_data."""

    @patch("modules.users.users_profile.router.profile_export_service.ExportService")
    @patch("modules.users.users_profile.router.profile_utils.sqlalchemy_obj_to_dict")
    @patch("modules.users.users_profile.router.users_crud.get_user_by_id")
    def test_success(
        self,
        mock_get_user,
        mock_to_dict,
        mock_export_service,
        profile_client,
    ):
        """Happy path: returns streaming ZIP."""
        mock_get_user.return_value = _make_user_mock()
        mock_to_dict.return_value = {"name": "Test", "password": "secret"}
        mock_instance = mock_export_service.return_value
        mock_instance.generate_export_archive.return_value = iter([b"zip-data"])

        response = profile_client.get(PREFIX + "/export")

        assert response.status_code == 200
        assert response.content == b"zip-data"

    @patch("modules.users.users_profile.router.profile_export_service.ExportService")
    @patch("modules.users.users_profile.router.profile_utils.sqlalchemy_obj_to_dict")
    @patch("modules.users.users_profile.router.users_crud.get_user_by_id")
    def test_user_not_found(
        self,
        mock_get_user,
        mock_to_dict,
        mock_export_service,
        profile_client,
    ):
        """Error: user not found → 404."""
        mock_get_user.return_value = None

        response = profile_client.get(PREFIX + "/export")

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"

    @patch("modules.users.users_profile.router.profile_export_service.ExportService")
    @patch("modules.users.users_profile.router.profile_utils.sqlalchemy_obj_to_dict")
    @patch("modules.users.users_profile.router.users_crud.get_user_by_id")
    def test_sensitive_fields_stripped(
        self,
        mock_get_user,
        mock_to_dict,
        mock_export_service,
        profile_client,
    ):
        """Verify sensitive fields are stripped from export dict."""
        mock_get_user.return_value = _make_user_mock()
        mock_to_dict.return_value = {
            "name": "Test",
            "password": "secret",
            "mfa_secret": "sec",
            "access_type": "admin",
        }
        mock_instance = mock_export_service.return_value
        mock_instance.generate_export_archive.return_value = iter([b"data"])

        response = profile_client.get(PREFIX + "/export")

        assert response.status_code == 200
        # Verify sensitive fields were popped before passing to service
        passed_dict = mock_instance.generate_export_archive.call_args[0][0]
        assert "password" not in passed_dict
        assert "mfa_secret" not in passed_dict
        assert "access_type" not in passed_dict
        assert passed_dict["name"] == "Test"

    @pytest.mark.parametrize(
        "exception_cls,expected_status",
        [
            (profile_exceptions.DatabaseConnectionError, 503),
            (profile_exceptions.FileSystemError, 507),
            (profile_exceptions.ZipCreationError, 422),
            (profile_exceptions.MemoryAllocationError, 507),
            (profile_exceptions.DataCollectionError, 422),
            (profile_exceptions.ExportTimeoutError, 408),
        ],
    )
    @patch("modules.users.users_profile.router.profile_export_service.ExportService")
    @patch("modules.users.users_profile.router.profile_utils.sqlalchemy_obj_to_dict")
    @patch("modules.users.users_profile.router.users_crud.get_user_by_id")
    def test_export_exceptions(
        self,
        mock_get_user,
        mock_to_dict,
        mock_export_service,
        exception_cls,
        expected_status,
        profile_client,
    ):
        """Each export exception is translated to the correct HTTP error via handle_import_export_exception."""
        mock_get_user.return_value = _make_user_mock()
        mock_to_dict.return_value = {"name": "Test"}
        mock_instance = mock_export_service.return_value
        mock_instance.generate_export_archive.side_effect = exception_cls("test error")

        response = profile_client.get(PREFIX + "/export")

        assert response.status_code == expected_status

    @patch("modules.users.users_profile.router.profile_export_service.ExportService")
    @patch("modules.users.users_profile.router.profile_utils.sqlalchemy_obj_to_dict")
    @patch("modules.users.users_profile.router.users_crud.get_user_by_id")
    def test_unexpected_exception(
        self,
        mock_get_user,
        mock_to_dict,
        mock_export_service,
        profile_client,
    ):
        """Unexpected exception → 500."""
        mock_get_user.return_value = _make_user_mock()
        mock_to_dict.return_value = {"name": "Test"}
        mock_instance = mock_export_service.return_value
        mock_instance.generate_export_archive.side_effect = RuntimeError("unexpected")

        response = profile_client.get(PREFIX + "/export")

        assert response.status_code == 500
        assert response.json()["detail"] == "Internal Server Error"


# ===================================================================
# POST /profile/import
# ===================================================================


class TestImportProfileData:
    """Tests for POST /profile/import — import_profile_data."""

    @patch("modules.users.users_profile.router.profile_import_service.ImportService")
    @patch("modules.users.users_profile.router.core_file_uploads.validate_upload", new_callable=AsyncMock)
    def test_success(
        self,
        mock_validate,
        mock_import_service,
        profile_client,
    ):
        """Happy path: import ZIP data."""
        mock_validate.return_value = None
        mock_instance = mock_import_service.return_value
        mock_instance.import_from_zip_data = AsyncMock(
            return_value={
                "imported": {"activities": 5},
            }
        )

        response = profile_client.post(
            PREFIX + "/import",
            files={"file": ("test.zip", b"zip-data", "application/zip")},
        )

        assert response.status_code == 201
        assert response.json()["imported"]["activities"] == 5

    @pytest.mark.parametrize(
        "exc,expected_status",
        [
            (profile_exceptions.ImportValidationError("test"), 400),
            (profile_exceptions.FileFormatError("test"), 400),
            (profile_exceptions.FileSizeError("test"), 413),
            (profile_exceptions.ActivityLimitError("test"), 413),
            (profile_exceptions.ZipStructureError("test"), 400),
            (profile_exceptions.JSONParseError("test"), 400),
            (profile_exceptions.SchemaValidationError("test"), 400),
        ],
    )
    @patch("modules.users.users_profile.router.profile_import_service.ImportService")
    @patch("modules.users.users_profile.router.core_file_uploads.validate_upload", new_callable=AsyncMock)
    def test_import_validation_exceptions(
        self,
        mock_validate,
        mock_import_service,
        exc,
        expected_status,
        profile_client,
    ):
        """Import validation errors mapped to correct HTTP status."""
        mock_validate.return_value = None
        mock_instance = mock_import_service.return_value
        mock_instance.import_from_zip_data = AsyncMock(side_effect=exc)

        response = profile_client.post(
            PREFIX + "/import",
            files={"file": ("test.zip", b"data", "application/zip")},
        )

        assert response.status_code == expected_status

    @pytest.mark.parametrize(
        "exc,expected_status",
        [
            (profile_exceptions.DataIntegrityError("test"), 422),
            (profile_exceptions.ImportTimeoutError("test"), 408),
            (profile_exceptions.DiskSpaceError("test"), 507),
        ],
    )
    @patch("modules.users.users_profile.router.profile_import_service.ImportService")
    @patch("modules.users.users_profile.router.core_file_uploads.validate_upload", new_callable=AsyncMock)
    def test_import_operation_exceptions(
        self,
        mock_validate,
        mock_import_service,
        exc,
        expected_status,
        profile_client,
    ):
        """Import operation errors mapped to correct HTTP status."""
        mock_validate.return_value = None
        mock_instance = mock_import_service.return_value
        mock_instance.import_from_zip_data = AsyncMock(side_effect=exc)

        response = profile_client.post(
            PREFIX + "/import",
            files={"file": ("test.zip", b"data", "application/zip")},
        )

        assert response.status_code == expected_status

    @patch("modules.users.users_profile.router.profile_import_service.ImportService")
    @patch("modules.users.users_profile.router.core_file_uploads.validate_upload", new_callable=AsyncMock)
    def test_value_error(
        self,
        mock_validate,
        mock_import_service,
        profile_client,
    ):
        """ValueError → 400."""
        mock_validate.return_value = None
        mock_instance = mock_import_service.return_value
        mock_instance.import_from_zip_data = AsyncMock(side_effect=ValueError("bad data"))

        response = profile_client.post(
            PREFIX + "/import",
            files={"file": ("test.zip", b"data", "application/zip")},
        )

        assert response.status_code == 400

    @pytest.mark.parametrize(
        "exc,expected_status",
        [
            (profile_exceptions.MemoryAllocationError("test"), 507),
            (MemoryError("test"), 500),
        ],
    )
    @patch("modules.users.users_profile.router.profile_import_service.ImportService")
    @patch("modules.users.users_profile.router.core_file_uploads.validate_upload", new_callable=AsyncMock)
    def test_memory_errors(
        self,
        mock_validate,
        mock_import_service,
        exc,
        expected_status,
        profile_client,
    ):
        """Memory errors mapped to correct HTTP status."""
        mock_validate.return_value = None
        mock_instance = mock_import_service.return_value
        mock_instance.import_from_zip_data = AsyncMock(side_effect=exc)

        response = profile_client.post(
            PREFIX + "/import",
            files={"file": ("test.zip", b"data", "application/zip")},
        )

        assert response.status_code == expected_status

    @pytest.mark.parametrize(
        "exc,expected_status",
        [
            (profile_exceptions.DatabaseConnectionError("test"), 503),
            (profile_exceptions.FileSystemError("test"), 507),
            (profile_exceptions.ZipCreationError("test"), 422),
            (profile_exceptions.DataCollectionError("test"), 422),
            (profile_exceptions.ExportTimeoutError("test"), 408),
        ],
    )
    @patch("modules.users.users_profile.router.profile_import_service.ImportService")
    @patch("modules.users.users_profile.router.core_file_uploads.validate_upload", new_callable=AsyncMock)
    def test_import_system_errors(
        self,
        mock_validate,
        mock_import_service,
        exc,
        expected_status,
        profile_client,
    ):
        """Import system errors (overlap with export) → mapped status."""
        mock_validate.return_value = None
        mock_instance = mock_import_service.return_value
        mock_instance.import_from_zip_data = AsyncMock(side_effect=exc)

        response = profile_client.post(
            PREFIX + "/import",
            files={"file": ("test.zip", b"data", "application/zip")},
        )

        assert response.status_code == expected_status

    @patch("modules.users.users_profile.router.profile_import_service.ImportService")
    @patch("modules.users.users_profile.router.core_file_uploads.validate_upload", new_callable=AsyncMock)
    def test_unexpected_exception(
        self,
        mock_validate,
        mock_import_service,
        profile_client,
    ):
        """Unexpected exception → 500."""
        mock_validate.return_value = None
        mock_instance = mock_import_service.return_value
        mock_instance.import_from_zip_data = AsyncMock(side_effect=RuntimeError("boom"))

        response = profile_client.post(
            PREFIX + "/import",
            files={"file": ("test.zip", b"data", "application/zip")},
        )

        assert response.status_code == 500
        assert "Import failed" in response.json()["detail"]


# ===================================================================
# GET /profile/mfa/status
# ===================================================================


class TestGetMFAStatus:
    """Tests for GET /profile/mfa/status — get_mfa_status."""

    def test_enabled(self, profile_client, mock_identity_service):
        """Returns enabled=True."""
        mock_identity_service.get_mfa_status.return_value = {"mfa_enabled": True}

        response = profile_client.get(PREFIX + "/mfa/status")

        assert response.status_code == 200
        assert response.json()["mfa_enabled"] is True

    def test_disabled(self, profile_client, mock_identity_service):
        """Returns enabled=False."""
        mock_identity_service.get_mfa_status.return_value = {"mfa_enabled": False}

        response = profile_client.get(PREFIX + "/mfa/status")

        assert response.status_code == 200
        assert response.json()["mfa_enabled"] is False


# ===================================================================
# GET /profile/mfa/backup-codes/status
# ===================================================================


class TestGetBackupCodeStatus:
    """Tests for GET /profile/mfa/backup-codes/status — get_backup_code_status."""

    def test_no_codes(self, profile_client, mock_identity_service):
        """No backup codes → has_codes=False."""
        mock_identity_service.get_backup_code_status.return_value = {
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

    def test_has_codes(self, profile_client, mock_identity_service):
        """Has backup codes with usage counts."""
        mock_identity_service.get_backup_code_status.return_value = {
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

    def test_success(self, profile_client, fake_mfa_secret_store, mock_identity_service):
        """Happy path: create MFA setup."""
        mock_identity_service.setup_mfa.return_value = mfa_schema.MFASetupResponse(
            secret="SECRETKEY",
            qr_code="base64qr",
            app_name="Endurain",
        )

        response = profile_client.post(PREFIX + "/mfa/setup")

        assert response.status_code == 201
        data = response.json()
        assert data["secret"] == "SECRETKEY"
        assert data["qr_code"] == "base64qr"

    def test_store_unavailable(self, profile_client, fake_mfa_secret_store, mock_identity_service):
        """MFA secret store unavailable → 503."""
        from modules.auth.mfa.setup_store import MFASecretStoreUnavailableError

        mock_identity_service.setup_mfa.side_effect = MFASecretStoreUnavailableError("store down")

        response = profile_client.post(PREFIX + "/mfa/setup")

        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"]


# ===================================================================
# PUT /profile/mfa/enable
# ===================================================================


class TestEnableMFA:
    """Tests for PUT /profile/mfa/enable — enable_mfa."""

    def test_success(self, profile_client, mock_identity_service):
        """Happy path: enable MFA."""
        mock_identity_service.enable_mfa.return_value = {
            "message": "MFA enabled successfully",
            "backup_codes": ["code1", "code2"],
        }

        response = profile_client.put(
            PREFIX + "/mfa/enable",
            json={"mfa_code": "123456", "current_password": "pass123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "MFA enabled successfully"
        assert data["backup_codes"] == ["code1", "code2"]

    def test_step_up_fails(self, profile_client, mock_identity_service):
        """Step-up fails before enabling."""
        mock_identity_service.enable_mfa.side_effect = HTTPException(status_code=401, detail="Invalid")

        response = profile_client.put(
            PREFIX + "/mfa/enable",
            json={"mfa_code": "123456", "current_password": "wrong"},
        )

        assert response.status_code == 401

    def test_no_setup_in_progress(self, profile_client, mock_identity_service):
        """No setup in progress → 400."""
        mock_identity_service.enable_mfa.side_effect = HTTPException(
            status_code=400,
            detail="No MFA setup in progress. Please run setup first.",
        )

        response = profile_client.put(
            PREFIX + "/mfa/enable",
            json={"mfa_code": "123456", "current_password": "pass123"},
        )

        assert response.status_code == 400
        assert "No MFA setup in progress" in response.json()["detail"]

    def test_get_secret_store_unavailable(self, profile_client, mock_identity_service):
        """get_secret raises MFASecretStoreUnavailableError → 503."""
        from modules.auth.mfa.setup_store import MFASecretStoreUnavailableError

        mock_identity_service.enable_mfa.side_effect = MFASecretStoreUnavailableError("store down")

        response = profile_client.put(
            PREFIX + "/mfa/enable",
            json={"mfa_code": "123456", "current_password": "pass123"},
        )

        assert response.status_code == 503

    def test_invalid_mfa_code(self, profile_client, mock_identity_service):
        """Invalid MFA code → 400."""
        mock_identity_service.enable_mfa.side_effect = HTTPException(
            status_code=400,
            detail="Invalid MFA code",
        )

        response = profile_client.put(
            PREFIX + "/mfa/enable",
            json={"mfa_code": "000000", "current_password": "pass123"},
        )

        assert response.status_code == 400

    def test_other_http_exception(self, profile_client, mock_identity_service):
        """Other HTTPException (not wrong code) → re-raised."""
        mock_identity_service.enable_mfa.side_effect = HTTPException(
            status_code=409,
            detail="MFA already enabled",
        )

        response = profile_client.put(
            PREFIX + "/mfa/enable",
            json={"mfa_code": "123456", "current_password": "pass123"},
        )

        assert response.status_code == 409


# ===================================================================
# PUT /profile/mfa/disable
# ===================================================================


class TestDisableMFA:
    """Tests for PUT /profile/mfa/disable — disable_mfa."""

    def test_success(self, profile_client, mock_identity_service):
        """Happy path: disable MFA."""
        mock_identity_service.disable_mfa.return_value = {"message": "MFA disabled successfully"}

        response = profile_client.put(
            PREFIX + "/mfa/disable",
            json={"mfa_code": "123456", "current_password": "pass123"},
        )

        assert response.status_code == 200
        assert response.json()["message"] == "MFA disabled successfully"

    def test_step_up_fails(self, profile_client, mock_identity_service):
        """Step-up fails before disable."""
        mock_identity_service.disable_mfa.side_effect = HTTPException(status_code=401, detail="Invalid")

        response = profile_client.put(
            PREFIX + "/mfa/disable",
            json={"mfa_code": "000000", "current_password": "wrong"},
        )

        assert response.status_code == 401


# ===================================================================
# POST /profile/mfa/verify
# ===================================================================


class TestVerifyMFA:
    """Tests for POST /profile/mfa/verify — verify_mfa."""

    def test_valid_code(self, profile_client, mock_identity_service):
        """Valid MFA code → success."""
        mock_identity_service.verify_mfa.return_value = {"message": "MFA code verified successfully"}

        response = profile_client.post(
            PREFIX + "/mfa/verify",
            json={"mfa_code": "123456"},
        )

        assert response.status_code == 200
        assert response.json()["message"] == "MFA code verified successfully"

    def test_invalid_code(self, profile_client, mock_identity_service):
        """Invalid MFA code → 400."""
        mock_identity_service.verify_mfa.side_effect = HTTPException(status_code=400, detail="Invalid MFA code")

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

    def test_success(self, profile_client, mock_identity_service):
        """Happy path: generate backup codes."""
        mock_identity_service.generate_backup_codes.return_value = {
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

    def test_user_not_found(self, profile_client, mock_identity_service):
        """User not found → 404."""
        mock_identity_service.generate_backup_codes.side_effect = HTTPException(
            status_code=404, detail="User not found"
        )

        response = profile_client.post(
            PREFIX + "/mfa/backup-codes",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 404

    def test_mfa_not_enabled(self, profile_client, mock_identity_service):
        """MFA not enabled → 400."""
        mock_identity_service.generate_backup_codes.side_effect = HTTPException(
            status_code=400,
            detail="MFA must be enabled to generate backup codes",
        )

        response = profile_client.post(
            PREFIX + "/mfa/backup-codes",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 400
        assert "MFA must be enabled" in response.json()["detail"]

    def test_step_up_fails(self, profile_client, mock_identity_service):
        """Step-up fails → 401."""
        mock_identity_service.generate_backup_codes.side_effect = HTTPException(status_code=401, detail="Invalid")

        response = profile_client.post(
            PREFIX + "/mfa/backup-codes",
            json={"current_password": "wrong"},
        )

        assert response.status_code == 401


# ===================================================================
# GET /profile/idp
# ===================================================================


class TestGetMyIdentityProviders:
    """Tests for GET /profile/idp — get_my_identity_providers."""

    def test_success(
        self,
        profile_client,
        mock_identity_service,
    ):
        """Happy path: returns enriched IdP links."""
        mock_identity_service.get_user_identity_provider_links.return_value = [
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

        response = profile_client.get(PREFIX + "/idp")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["idp_name"] == "TestIdP"

    def test_no_links(
        self,
        profile_client,
        mock_identity_service,
    ):
        """No IdP links → empty list."""
        mock_identity_service.get_user_identity_provider_links.return_value = []

        response = profile_client.get(PREFIX + "/idp")

        assert response.status_code == 200
        assert response.json() == []


# ===================================================================
# POST /profile/idp/{idp_id}/unlink
# ===================================================================


class TestDeleteMyIdentityProvider:
    """Tests for POST /profile/idp/{idp_id}/unlink — delete_my_identity_provider."""

    def test_success(self, profile_client, mock_identity_service):
        """Happy path: unlink IdP."""
        response = profile_client.post(
            PREFIX + "/idp/1/unlink",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 204
        mock_identity_service.delete_identity_provider_link.assert_called_once()

    def test_step_up_fails(self, profile_client, mock_identity_service):
        """Step-up fails → 401."""
        mock_identity_service.delete_identity_provider_link.side_effect = HTTPException(
            status_code=401, detail="Invalid"
        )

        response = profile_client.post(
            PREFIX + "/idp/1/unlink",
            json={"current_password": "wrong"},
        )

        assert response.status_code == 401

    def test_idp_not_found(self, profile_client, mock_identity_service):
        """IDP not found → 404."""
        mock_identity_service.delete_identity_provider_link.side_effect = HTTPException(
            status_code=404, detail="Identity provider not found"
        )

        response = profile_client.post(
            PREFIX + "/idp/1/unlink",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 404

    def test_link_not_found(self, profile_client, mock_identity_service):
        """Link not found for user → 404."""
        mock_identity_service.delete_identity_provider_link.side_effect = HTTPException(
            status_code=404, detail="Identity provider link missing"
        )

        response = profile_client.post(
            PREFIX + "/idp/1/unlink",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 404

    def test_account_lockout(self, profile_client, mock_identity_service):
        """Unlinking last auth method → 400."""
        mock_identity_service.delete_identity_provider_link.side_effect = HTTPException(
            status_code=400,
            detail="Cannot unlink last authentication method. Please set a password first.",
        )

        response = profile_client.post(
            PREFIX + "/idp/1/unlink",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 400
        assert "Cannot unlink" in response.json()["detail"]

    def test_deletion_fails(self, profile_client, mock_identity_service):
        """Deletion returns False → 500."""
        mock_identity_service.delete_identity_provider_link.side_effect = HTTPException(
            status_code=500, detail="Failed to unlink identity provider"
        )

        response = profile_client.post(
            PREFIX + "/idp/1/unlink",
            json={"current_password": "pass123"},
        )

        assert response.status_code == 500
        assert "Failed to unlink" in response.json()["detail"]
