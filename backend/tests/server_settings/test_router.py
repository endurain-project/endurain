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
import modules.auth.dependencies as auth_dependencies
import modules.auth.schema as auth_schema
import modules.server_settings.schema as server_settings_schema

VERIFIER = MagicMock()
STEP_UP = {"current_password": "admin-password"}


@pytest.fixture(autouse=True)
def _step_up_verifier(fast_api_app):
    """Install a stand-in for the calling administrator's step-up verifier."""
    fast_api_app.dependency_overrides[auth_dependencies.get_step_up_verifier] = lambda: VERIFIER


class TestReadServerSettings:
    """Test suite for read_server_settings endpoint."""

    @patch("modules.server_settings.router.server_settings_service.get_server_settings_for_admin")
    def test_read_server_settings_success(self, mock_get_settings, fast_api_client, fast_api_app):
        """Test successful retrieval of server settings."""
        # Arrange
        mock_settings = server_settings_schema.ServerSettingsAdminRead(
            id=1,
            version=4,
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
            tileserver_regenerate_thumbnails_on_change=False,
            password_length_regular_users=8,
            password_length_admin_users=12,
            tileserver_api_key_set=False,
            geocoding_service="nominatim",
            geocoding_host=None,
            geocoding_use_https=True,
            geocoding_rate_limit=1.0,
            session_idle_timeout_enabled=False,
            session_idle_timeout_hours=1,
            session_absolute_timeout_hours=24,
            access_token_expire_minutes=15,
            refresh_token_expire_days=7,
            api_key_max_lifetime_days=365,
            read_notification_retention_days=90,
            audit_retention_days=90,
            audit_legal_hold=False,
            geocoding_api_key_set=False,
            env_managed={},
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
            version=4,
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
            password_length_regular_users=10,
            password_length_admin_users=15,
            tileserver_regenerate_thumbnails_on_change=False,
            tileserver_api_key_set=False,
            geocoding_service="nominatim",
            geocoding_host=None,
            geocoding_use_https=True,
            geocoding_rate_limit=1.0,
            session_idle_timeout_enabled=False,
            session_idle_timeout_hours=1,
            session_absolute_timeout_hours=24,
            access_token_expire_minutes=15,
            refresh_token_expire_days=7,
            api_key_max_lifetime_days=365,
            read_notification_retention_days=90,
            audit_retention_days=90,
            audit_legal_hold=False,
            geocoding_api_key_set=False,
            env_managed={},
        )

        mock_edit_settings.return_value = mock_updated_settings

        # Act
        response = fast_api_client.put(
            "/server_settings",
            headers={**{"Authorization": "Bearer mock_token"}, "If-Match": '"1"'},
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
                "password_length_regular_users": 10,
                "password_length_admin_users": 15,
                "tileserver_regenerate_thumbnails_on_change": False,
                "geocoding_service": "nominatim",
                "geocoding_host": None,
                "geocoding_use_https": True,
                "geocoding_rate_limit": 1.0,
                "session_idle_timeout_enabled": False,
                "session_idle_timeout_hours": 1,
                "session_absolute_timeout_hours": 24,
                "access_token_expire_minutes": 15,
                "refresh_token_expire_days": 7,
                "api_key_max_lifetime_days": 365,
                "read_notification_retention_days": 90,
                "audit_retention_days": 90,
                "audit_legal_hold": False,
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["units"] == "imperial"
        assert data["num_records_per_page"] == 50
        assert "tileserver_api_key" not in data
        assert response.headers["etag"] == '"4"'
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
            headers={**{"Authorization": "Bearer mock_token"}, "If-Match": '"1"'},
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
                "password_length_regular_users": 10,
                "password_length_admin_users": 15,
                "tileserver_regenerate_thumbnails_on_change": False,
                "geocoding_service": "nominatim",
                "geocoding_host": None,
                "geocoding_use_https": True,
                "geocoding_rate_limit": 1.0,
                "session_idle_timeout_enabled": False,
                "session_idle_timeout_hours": 1,
                "session_absolute_timeout_hours": 24,
                "access_token_expire_minutes": 15,
                "refresh_token_expire_days": 7,
                "api_key_max_lifetime_days": 365,
                "read_notification_retention_days": 90,
                "audit_retention_days": 90,
                "audit_legal_hold": False,
            },
        )

        # Assert
        assert response.status_code == 404


class TestEditNeedsIfMatch:
    @pytest.mark.parametrize("path", ["/server_settings", "/server_settings/email/settings"])
    def test_an_edit_without_if_match_is_428(self, path, fast_api_client):
        response = fast_api_client.put(path, headers={"Authorization": "Bearer mock_token"}, json={})

        assert response.status_code == 428


def _edit_body(**overrides) -> dict:
    """A complete, valid edit body, the way the frontend sends it on every save."""
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
        "password_length_regular_users": 10,
        "password_length_admin_users": 15,
        "tileserver_regenerate_thumbnails_on_change": False,
        "geocoding_service": "nominatim",
        "geocoding_host": None,
        "geocoding_use_https": True,
        "geocoding_rate_limit": 1.0,
        "session_idle_timeout_enabled": False,
        "session_idle_timeout_hours": 1,
        "session_absolute_timeout_hours": 24,
        "access_token_expire_minutes": 15,
        "refresh_token_expire_days": 7,
        "api_key_max_lifetime_days": 365,
        "read_notification_retention_days": 90,
        "audit_retention_days": 90,
        "audit_legal_hold": False,
    }
    body.update(overrides)
    return body


class TestEditRejectsReadOnlyFields:
    """The edit body must not accept fields the route does not own."""

    @pytest.mark.parametrize("field,value", [("id", 2), ("login_photo_set", False)])
    def test_read_only_fields_are_a_422(self, field, value, fast_api_client, fast_api_app):
        body = _edit_body(**{field: value})
        response = fast_api_client.put(
            "/server_settings", headers={**{"Authorization": "Bearer mock_token"}, "If-Match": '"1"'}, json=body
        )
        assert response.status_code == 422


class TestEditValidatesAuditRetention:
    @pytest.mark.parametrize("days", [1, 29])
    def test_a_retention_below_the_floor_is_a_422_naming_the_rule(self, days, fast_api_client, fast_api_app):
        response = fast_api_client.put(
            "/server_settings",
            headers={"Authorization": "Bearer mock_token", "If-Match": '"1"'},
            json=_edit_body(audit_retention_days=days),
        )

        assert response.status_code == 422
        assert "Audit trail retention must be 0 or between 30 and 36500 days" in response.text


class TestUploadLoginPhoto:
    """Test suite for upload_login_photo endpoint."""

    @pytest.mark.parametrize(("replaced", "status_code"), [(False, 201), (True, 200)])
    @patch("modules.server_settings.router.server_settings_login_photo_service.upload_login_photo")
    def test_put_login_photo_answers_201_for_a_new_photo_and_200_for_a_replacement(
        self, mock_upload, replaced, status_code, fast_api_client, fast_api_app
    ):
        """A put stores the photo and names the version that now identifies it."""
        mock_upload.return_value = (server_settings_schema.LoginPhotoRead(version=4), replaced)

        response = fast_api_client.put(
            "/server_settings/login-photo",
            headers={"Authorization": "Bearer mock_token"},
            files={"file": ("login.png", b"png", "image/png")},
        )

        assert response.status_code == status_code
        assert response.json() == {"version": 4}


class TestDeleteLoginPhoto:
    """Test suite for delete_login_photo endpoint."""

    @patch("modules.server_settings.router.server_settings_login_photo_service.delete_login_photo")
    def test_delete_login_photo_success(self, mock_delete, fast_api_client, fast_api_app):
        """Test successful deletion of login photo."""
        # Act
        response = fast_api_client.delete(
            "/server_settings/login-photo",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 204

    @patch("modules.server_settings.router.server_settings_login_photo_service.delete_login_photo")
    def test_delete_login_photo_not_exists(self, mock_delete, fast_api_client, fast_api_app):
        """Test deletion when photo doesn't exist."""
        # Act
        response = fast_api_client.delete(
            "/server_settings/login-photo",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 204


class TestEmail:
    """Test suite for the email status and test-send endpoints."""

    @patch("modules.server_settings.router.server_settings_mail_service.get_email_status")
    def test_read_email_status(self, mock_status, fast_api_client):
        mock_status.return_value = server_settings_schema.EmailStatus(configured=False, problems=["Host is not set"])

        response = fast_api_client.get("/server_settings/email", headers={"Authorization": "Bearer mock_token"})

        assert response.status_code == 200
        assert response.json() == {"configured": False, "problems": ["Host is not set"]}

    @patch("modules.server_settings.router.server_settings_mail_service.send_test_email")
    @patch("modules.server_settings.router.users_integration.get_user")
    def test_send_test_email_sends_to_the_caller(self, mock_get_user, mock_send, fast_api_client, fast_api_app):
        mock_get_user.return_value = MagicMock(email="admin@example.com")
        mail = MagicMock()
        fast_api_app.dependency_overrides[core_dependencies.get_mail] = lambda: mail

        response = fast_api_client.post("/server_settings/email/test", headers={"Authorization": "Bearer mock_token"})

        assert response.status_code == 204
        assert response.content == b""
        mock_send.assert_called_once()
        assert mock_send.call_args.args[:2] == (mock_get_user.return_value, mail)

    @patch("modules.server_settings.router.server_settings_mail_service.send_test_email")
    @patch("modules.server_settings.router.users_integration.get_user")
    def test_send_test_email_maps_unconfigured_to_503(self, mock_get_user, mock_send, fast_api_app):
        mock_get_user.return_value = MagicMock(email="admin@example.com")
        mock_send.side_effect = core_exceptions.ServiceUnavailableError("Email is not configured: Host is not set")

        core_exceptions.register_exception_handlers(fast_api_app)
        client = TestClient(fast_api_app)

        response = client.post("/server_settings/email/test", headers={"Authorization": "Bearer mock_token"})

        assert response.status_code == 503
        assert "Host is not set" in response.text

    @patch("modules.server_settings.router.server_settings_mail_service.send_test_email")
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


def _mail_admin_read(**overrides) -> server_settings_schema.MailSettingsAdminRead:
    values = dict(
        id=1,
        version=1,
        host="mail.example.com",
        port=587,
        security="starttls",
        username="me@example.com",
        from_address=None,
        password_set=True,
        env_managed={},
    )
    values.update(overrides)
    return server_settings_schema.MailSettingsAdminRead(**values)


def _route_scopes(path: str, method: str) -> set[str]:
    """The scopes the route's ``check_scopes`` dependency requires."""
    import modules.server_settings.router as server_settings_router

    route = next(r for r in server_settings_router.router.routes if r.path == path and method in r.methods)
    return {scope for dep in route.dependant.dependencies for scope in dep.own_oauth_scopes or []}


class TestMailSettingsRoutes:
    """Test suite for the mail settings endpoints."""

    def test_the_routes_require_the_server_settings_scopes(self):
        assert _route_scopes("/email/settings", "GET") == {"server_settings:read"}
        assert _route_scopes("/email/settings", "PUT") == {"server_settings:write"}

    @patch("modules.server_settings.router.server_settings_mail_service.get_mail_settings_for_admin")
    def test_read_returns_the_settings_and_env_managed(self, mock_get, fast_api_client):
        mock_get.return_value = _mail_admin_read(env_managed={"host": "SMTP_HOST"})

        response = fast_api_client.get(
            "/server_settings/email/settings", headers={"Authorization": "Bearer mock_token"}
        )

        assert response.status_code == 200
        assert response.json()["host"] == "mail.example.com"
        assert response.json()["env_managed"] == {"host": "SMTP_HOST"}
        assert response.json()["password_set"] is True
        assert "password" not in response.json()

    @patch("modules.server_settings.router.server_settings_mail_service.edit_mail_settings")
    def test_edit_never_returns_the_password(self, mock_edit, fast_api_client):
        mock_edit.return_value = _mail_admin_read()
        body = {
            "host": "mail.example.com",
            "port": 587,
            "security": "starttls",
            "username": "me@example.com",
            "from_address": None,
            "password": "super-secret-value",
            "step_up": STEP_UP,
        }

        response = fast_api_client.put(
            "/server_settings/email/settings",
            json=body,
            headers={**{"Authorization": "Bearer mock_token"}, "If-Match": '"1"'},
        )

        assert response.status_code == 200
        assert "super-secret-value" not in response.text
        assert "password" not in response.json()
        sent = mock_edit.call_args.args[0]
        assert sent.password == "super-secret-value"

    @patch("modules.server_settings.router.server_settings_mail_service.edit_mail_settings")
    def test_edit_of_an_env_managed_field_is_a_400(self, mock_edit, fast_api_app):
        mock_edit.side_effect = core_exceptions.InvalidInputError("host is set by the SMTP_HOST environment variable")
        core_exceptions.register_exception_handlers(fast_api_app)
        body = {
            "host": "x.example.com",
            "port": 587,
            "security": "starttls",
            "username": None,
            "from_address": None,
            "step_up": STEP_UP,
        }

        response = TestClient(fast_api_app).put(
            "/server_settings/email/settings",
            json=body,
            headers={**{"Authorization": "Bearer mock_token"}, "If-Match": '"1"'},
        )

        assert response.status_code == 400
        assert "SMTP_HOST" in response.text

    @pytest.mark.parametrize(
        "override",
        [{"port": 0}, {"port": 70000}, {"security": "tls"}, {"unknown": 1}],
    )
    def test_edit_rejects_invalid_bodies(self, fast_api_client, override):
        body = {
            "host": "mail.example.com",
            "port": 587,
            "security": "starttls",
            "username": None,
            "from_address": None,
            "step_up": STEP_UP,
        }
        body.update(override)

        response = fast_api_client.put(
            "/server_settings/email/settings",
            json=body,
            headers={**{"Authorization": "Bearer mock_token"}, "If-Match": '"1"'},
        )

        assert response.status_code == 422

    @patch("modules.server_settings.router.server_settings_mail_service.edit_mail_settings")
    def test_a_blank_host_is_sent_on_as_unset(self, mock_edit, fast_api_client):
        mock_edit.return_value = _mail_admin_read(host=None)
        body = {
            "host": "  ",
            "port": 587,
            "security": "starttls",
            "username": "",
            "from_address": "",
            "step_up": STEP_UP,
        }

        fast_api_client.put(
            "/server_settings/email/settings",
            json=body,
            headers={**{"Authorization": "Bearer mock_token"}, "If-Match": '"1"'},
        )

        sent = mock_edit.call_args.args[0]
        assert (sent.host, sent.username, sent.from_address) == (None, None, None)


class TestMailSettingsStepUp:
    """Editing the mail settings needs the administrator's step-up, which is not a setting."""

    @staticmethod
    def _body(**extra):
        body = {"host": "mail.example.com", "port": 587, "security": "starttls", "username": None, "from_address": None}
        body.update(extra)
        return body

    @staticmethod
    def _put(client, body):
        return client.put(
            "/server_settings/email/settings",
            json=body,
            headers={"Authorization": "Bearer mock_token", "If-Match": '"1"'},
        )

    @patch("modules.server_settings.router.server_settings_mail_service.edit_mail_settings")
    def test_a_body_without_a_step_up_is_422_and_never_reaches_the_service(self, mock_edit, fast_api_client):
        response = self._put(fast_api_client, self._body())

        assert response.status_code == 422
        mock_edit.assert_not_called()

    @patch("modules.server_settings.router.server_settings_mail_service.edit_mail_settings")
    def test_the_service_gets_the_settings_without_the_step_up_then_the_step_up_and_verifier(
        self, mock_edit, fast_api_client
    ):
        mock_edit.return_value = _mail_admin_read()

        response = self._put(fast_api_client, self._body(password="pw", step_up=STEP_UP))

        assert response.status_code == 200
        attributes, step_up, verifier = mock_edit.call_args.args[:3]
        assert type(attributes) is server_settings_schema.MailSettingsEdit
        assert "step_up" not in attributes.model_dump()
        assert attributes.model_fields_set == {"host", "port", "security", "username", "from_address", "password"}
        assert step_up == auth_schema.StepUpVerification(current_password="admin-password")
        assert verifier is VERIFIER
        assert "admin-password" not in response.text

    @patch("modules.server_settings.router.server_settings_mail_service.edit_mail_settings")
    def test_a_refused_step_up_is_403_step_up_failed(self, mock_edit, fast_api_client):
        mock_edit.side_effect = core_exceptions.StepUpFailedError()

        response = self._put(fast_api_client, self._body(step_up=STEP_UP))

        assert response.status_code == 403
        assert response.json()["type"] == "urn:endurain:error:step-up-failed"
