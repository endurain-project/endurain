"""
Tests for server_settings.router module.

This module tests API endpoints for server settings management,
including read, update, and file upload operations.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import modules.server_settings.schema as server_settings_schema


class TestReadServerSettings:
    """Test suite for read_server_settings endpoint."""

    @patch("modules.server_settings.router.server_settings_service.get_server_settings_for_admin")
    def test_read_server_settings_success(self, mock_get_settings, fast_api_client, fast_api_app):
        """Test successful retrieval of server settings."""
        # Arrange
        mock_settings = server_settings_schema.ServerSettingsAdminRead(
            id=1,
            units=server_settings_schema.Units.METRIC,
            public_shareable_links=False,
            public_shareable_links_user_info=False,
            login_photo_set=False,
            currency=server_settings_schema.Currency.EURO,
            num_records_per_page=25,
            signup_enabled=False,
            signup_require_admin_approval=True,
            signup_require_email_verification=True,
            sso_enabled=False,
            local_login_enabled=True,
            sso_auto_redirect=False,
            tileserver_url="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            tileserver_attribution="&copy; OpenStreetMap",
            map_background_color="#dddddd",
            password_type="strict",
            tileserver_regenerate_thumbnails_on_change=False,
            password_length_regular_users=8,
            password_length_admin_users=12,
            tileserver_api_key_set=False,
        )

        mock_get_settings.return_value = mock_settings

        # Act
        response = fast_api_client.get(
            "/server_settings",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["units"] == "metric"
        assert data["public_shareable_links"] is False

    @patch("modules.server_settings.router.server_settings_service.get_server_settings_for_admin")
    def test_read_server_settings_not_found(self, mock_get_settings, fast_api_client, fast_api_app):
        """Test retrieval when settings not found."""
        # Arrange
        mock_get_settings.side_effect = core_exceptions.NotFoundError("Server settings not found")
        core_exceptions.register_exception_handlers(fast_api_app)

        # Act
        response = fast_api_client.get(
            "/server_settings",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404


class TestEditServerSettings:
    """Test suite for edit_server_settings endpoint."""

    @patch("modules.server_settings.router.server_settings_service.edit_server_settings")
    def test_edit_server_settings_success(self, mock_edit_settings, fast_api_client, fast_api_app):
        """Test successful update of server settings."""
        # Arrange
        mock_updated_settings = server_settings_schema.ServerSettingsAdminRead(
            id=1,
            units="imperial",
            public_shareable_links=True,
            public_shareable_links_user_info=True,
            login_photo_set=False,
            currency="dollar",
            num_records_per_page=50,
            signup_enabled=True,
            signup_require_admin_approval=False,
            signup_require_email_verification=True,
            sso_enabled=False,
            local_login_enabled=True,
            sso_auto_redirect=False,
            tileserver_url="https://tiles.example.com/{z}/{x}/{y}.png",
            tileserver_attribution="&copy; Example",
            map_background_color="#000000",
            password_type="length_only",
            password_length_regular_users=10,
            password_length_admin_users=15,
            tileserver_regenerate_thumbnails_on_change=False,
            tileserver_api_key_set=False,
        )

        mock_edit_settings.return_value = mock_updated_settings

        # Act
        response = fast_api_client.put(
            "/server_settings",
            headers={"Authorization": "Bearer mock_token"},
            json={
                "units": "imperial",
                "public_shareable_links": True,
                "public_shareable_links_user_info": True,
                "currency": "dollar",
                "num_records_per_page": 50,
                "signup_enabled": True,
                "signup_require_admin_approval": False,
                "signup_require_email_verification": True,
                "sso_enabled": False,
                "local_login_enabled": True,
                "sso_auto_redirect": False,
                "tileserver_url": "https://tiles.example.com/{z}/{x}/{y}.png",
                "tileserver_attribution": "&copy; Example",
                "map_background_color": "#000000",
                "password_type": "length_only",
                "password_length_regular_users": 10,
                "password_length_admin_users": 15,
                "tileserver_regenerate_thumbnails_on_change": False,
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["units"] == "imperial"
        assert data["num_records_per_page"] == 50
        assert "tileserver_api_key" not in data
        assert fast_api_app.state.allowed_tile_domains[-1] == "https://tiles.example.com"

    @patch("modules.server_settings.router.server_settings_service.edit_server_settings")
    def test_edit_server_settings_not_found(self, mock_edit_settings, fast_api_client, fast_api_app):
        """Test update when settings not found."""
        # Arrange
        mock_edit_settings.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server settings not found",
        )

        # Act
        response = fast_api_client.put(
            "/server_settings",
            headers={"Authorization": "Bearer mock_token"},
            json={
                "units": "imperial",
                "public_shareable_links": True,
                "public_shareable_links_user_info": True,
                "currency": "dollar",
                "num_records_per_page": 50,
                "signup_enabled": True,
                "signup_require_admin_approval": False,
                "signup_require_email_verification": True,
                "sso_enabled": False,
                "local_login_enabled": True,
                "sso_auto_redirect": False,
                "tileserver_url": "https://tiles.example.com/{z}/{x}/{y}.png",
                "tileserver_attribution": "&copy; Example",
                "map_background_color": "#000000",
                "password_type": "length_only",
                "password_length_regular_users": 10,
                "password_length_admin_users": 15,
                "tileserver_regenerate_thumbnails_on_change": False,
            },
        )

        # Assert
        assert response.status_code == 404


class TestEditRejectsReadOnlyFields:
    """The edit body must not accept fields the route does not own."""

    @pytest.mark.parametrize("field,value", [("id", 2), ("login_photo_set", False)])
    def test_read_only_fields_are_a_422(self, field, value, fast_api_client, fast_api_app):
        body = {
            "units": "imperial",
            "public_shareable_links": True,
            "public_shareable_links_user_info": True,
            "currency": "dollar",
            "num_records_per_page": 50,
            "signup_enabled": True,
            "signup_require_admin_approval": False,
            "signup_require_email_verification": True,
            "sso_enabled": False,
            "local_login_enabled": True,
            "sso_auto_redirect": False,
            "tileserver_url": "https://tiles.example.com/{z}/{x}/{y}.png",
            "tileserver_attribution": "&copy; Example",
            "map_background_color": "#000000",
            "password_type": "length_only",
            "password_length_regular_users": 10,
            "password_length_admin_users": 15,
            "tileserver_regenerate_thumbnails_on_change": False,
            field: value,
        }
        response = fast_api_client.put("/server_settings", headers={"Authorization": "Bearer mock_token"}, json=body)
        assert response.status_code == 422


class TestDeleteLoginPhoto:
    """Test suite for delete_login_photo endpoint."""

    @patch("modules.server_settings.router.server_settings_service.delete_login_photo")
    def test_delete_login_photo_success(self, mock_delete, fast_api_client, fast_api_app):
        """Test successful deletion of login photo."""
        # Act
        response = fast_api_client.delete(
            "/server_settings/upload/login",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 204

    @patch("modules.server_settings.router.server_settings_service.delete_login_photo")
    def test_delete_login_photo_not_exists(self, mock_delete, fast_api_client, fast_api_app):
        """Test deletion when photo doesn't exist."""
        # Act
        response = fast_api_client.delete(
            "/server_settings/upload/login",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 204


class TestEmail:
    """Test suite for the email status and test-send endpoints."""

    @patch("modules.server_settings.router.server_settings_service.get_email_status")
    def test_read_email_status(self, mock_status, fast_api_client):
        mock_status.return_value = server_settings_schema.EmailStatus(
            configured=False, problems=["SMTP_HOST is not set"]
        )

        response = fast_api_client.get("/server_settings/email", headers={"Authorization": "Bearer mock_token"})

        assert response.status_code == 200
        assert response.json() == {"configured": False, "problems": ["SMTP_HOST is not set"]}

    @patch("modules.server_settings.router.server_settings_service.send_test_email")
    @patch("modules.server_settings.router.users_integration.get_user")
    def test_send_test_email_sends_to_the_caller(self, mock_get_user, mock_send, fast_api_client, fast_api_app):
        mock_get_user.return_value = MagicMock(email="admin@example.com")
        mail = MagicMock()
        fast_api_app.dependency_overrides[core_dependencies.get_mail] = lambda: mail

        response = fast_api_client.post("/server_settings/email/test", headers={"Authorization": "Bearer mock_token"})

        assert response.status_code == 200
        assert response.json() == {"message": "Test email sent to admin@example.com."}
        mock_send.assert_called_once_with(mock_get_user.return_value, mail)

    @patch("modules.server_settings.router.server_settings_service.send_test_email")
    @patch("modules.server_settings.router.users_integration.get_user")
    def test_send_test_email_maps_unconfigured_to_503(self, mock_get_user, mock_send, fast_api_app):
        mock_get_user.return_value = MagicMock(email="admin@example.com")
        mock_send.side_effect = core_exceptions.ServiceUnavailableError("Email is not configured: SMTP_HOST is not set")

        core_exceptions.register_exception_handlers(fast_api_app)
        client = TestClient(fast_api_app)

        response = client.post("/server_settings/email/test", headers={"Authorization": "Bearer mock_token"})

        assert response.status_code == 503
        assert "SMTP_HOST is not set" in response.text

    @patch("modules.server_settings.router.server_settings_service.send_test_email")
    @patch("modules.server_settings.router.users_integration.get_user")
    def test_send_test_email_maps_delivery_failure_to_502(self, mock_get_user, mock_send, fast_api_app):
        mock_get_user.return_value = MagicMock(email="admin@example.com")
        mock_send.side_effect = core_exceptions.UpstreamError(
            "The mail server did not accept the test email: status 535"
        )

        core_exceptions.register_exception_handlers(fast_api_app)
        client = TestClient(fast_api_app)

        response = client.post("/server_settings/email/test", headers={"Authorization": "Bearer mock_token"})

        assert response.status_code == 502
        assert "status 535" in response.text
