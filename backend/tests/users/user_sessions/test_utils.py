import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, PropertyMock
from fastapi import HTTPException

import users.users_sessions.utils as users_session_utils
import users.users_sessions.schema as users_session_schema
import users.users_sessions.models as users_session_models
import users.users.schema as users_schema


class TestDeviceTypeEnum:
    """
    Test suite for DeviceType enum.
    """

    def test_device_type_mobile_value(self):
        """
        Test DeviceType.MOBILE has correct value.
        """
        # Assert
        assert users_session_utils.DeviceType.MOBILE.value == "Mobile"

    def test_device_type_tablet_value(self):
        """
        Test DeviceType.TABLET has correct value.
        """
        # Assert
        assert users_session_utils.DeviceType.TABLET.value == "Tablet"

    def test_device_type_pc_value(self):
        """
        Test DeviceType.PC has correct value.
        """
        # Assert
        assert users_session_utils.DeviceType.PC.value == "PC"


class TestDeviceInfo:
    """
    Test suite for DeviceInfo dataclass.
    """

    def test_device_info_creation(self):
        """
        Test DeviceInfo dataclass creation.
        """
        # Arrange & Act
        device_info = users_session_utils.DeviceInfo(
            device_type=users_session_utils.DeviceType.PC,
            operating_system="Windows",
            operating_system_version="10",
            browser="Chrome",
            browser_version="120.0",
        )

        # Assert
        assert device_info.device_type == users_session_utils.DeviceType.PC
        assert device_info.operating_system == "Windows"
        assert device_info.operating_system_version == "10"
        assert device_info.browser == "Chrome"
        assert device_info.browser_version == "120.0"


class TestValidateSessionTimeout:
    """
    Test suite for validate_session_timeout function.
    """

    @patch(
        "users.users_sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_ENABLED", True
    )
    @patch("users.users_sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_HOURS", 1)
    @patch(
        "users.users_sessions.utils.auth_constants.SESSION_ABSOLUTE_TIMEOUT_HOURS", 24
    )
    def test_validate_session_timeout_valid(self):
        """
        Test valid session passes timeout validation.
        """
        # Arrange
        now = datetime.now(timezone.utc)
        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_session.last_activity_at = now - timedelta(minutes=30)
        mock_session.created_at = now - timedelta(hours=12)

        # Act & Assert (should not raise)
        users_session_utils.validate_session_timeout(mock_session)

    @patch(
        "users.users_sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_ENABLED", True
    )
    @patch("users.users_sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_HOURS", 1)
    @patch(
        "users.users_sessions.utils.auth_constants.SESSION_ABSOLUTE_TIMEOUT_HOURS", 24
    )
    def test_validate_session_timeout_idle_expired(self):
        """
        Test session with idle timeout raises exception.
        """
        # Arrange
        now = datetime.now(timezone.utc)
        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_session.last_activity_at = now - timedelta(hours=2)
        mock_session.created_at = now - timedelta(hours=12)

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            users_session_utils.validate_session_timeout(mock_session)

        assert exc_info.value.status_code == 401
        assert "inactivity" in exc_info.value.detail

    @patch(
        "users.users_sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_ENABLED", True
    )
    @patch("users.users_sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_HOURS", 1)
    @patch(
        "users.users_sessions.utils.auth_constants.SESSION_ABSOLUTE_TIMEOUT_HOURS", 24
    )
    def test_validate_session_timeout_absolute_expired(self):
        """
        Test session with absolute timeout raises exception.
        """
        # Arrange
        now = datetime.now(timezone.utc)
        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_session.last_activity_at = now - timedelta(minutes=30)
        mock_session.created_at = now - timedelta(hours=30)

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            users_session_utils.validate_session_timeout(mock_session)

        assert exc_info.value.status_code == 401
        assert "security" in exc_info.value.detail.lower()

    @patch(
        "users.users_sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_ENABLED", False
    )
    def test_validate_session_timeout_disabled(self):
        """
        Test timeout validation is skipped when disabled.
        """
        # Arrange
        now = datetime.now(timezone.utc)
        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_session.last_activity_at = now - timedelta(hours=100)
        mock_session.created_at = now - timedelta(hours=200)

        # Act & Assert (should not raise even with expired times)
        users_session_utils.validate_session_timeout(mock_session)


class TestGetUserAgent:
    """
    Test suite for get_user_agent function.
    """

    def test_get_user_agent_with_header(self):
        """
        Test extracting user agent from request headers.
        """
        # Arrange
        mock_request = MagicMock()
        mock_request.headers.get.return_value = "Mozilla/5.0"

        # Act
        result = users_session_utils.get_user_agent(mock_request)

        # Assert
        assert result == "Mozilla/5.0"

    def test_get_user_agent_without_header(self):
        """
        Test extracting user agent when header missing.
        """
        # Arrange
        mock_request = MagicMock()
        mock_request.headers.get.return_value = ""

        # Act
        result = users_session_utils.get_user_agent(mock_request)

        # Assert
        assert result == ""


class TestGetIpAddress:
    """
    Test suite for get_ip_address function.
    """

    def test_get_ip_address_from_forwarded_for(self):
        """
        Test extracting IP from X-Forwarded-For header.
        """
        # Arrange
        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda h: (
            "192.168.1.1, 10.0.0.1" if h == "X-Forwarded-For" else None
        )

        # Act
        result = users_session_utils.get_ip_address(mock_request)

        # Assert
        assert result == "192.168.1.1"

    def test_get_ip_address_from_real_ip(self):
        """
        Test extracting IP from X-Real-IP header.
        """
        # Arrange
        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda h: (
            "10.0.0.1" if h == "X-Real-IP" else None
        )

        # Act
        result = users_session_utils.get_ip_address(mock_request)

        # Assert
        assert result == "10.0.0.1"

    def test_get_ip_address_from_client(self):
        """
        Test extracting IP from request client.
        """
        # Arrange
        mock_request = MagicMock()
        mock_request.headers.get.return_value = None
        mock_request.client.host = "127.0.0.1"

        # Act
        result = users_session_utils.get_ip_address(mock_request)

        # Assert
        assert result == "127.0.0.1"

    def test_get_ip_address_no_client(self):
        """
        Test extracting IP when no client available.
        """
        # Arrange
        mock_request = MagicMock()
        mock_request.headers.get.return_value = None
        mock_request.client = None

        # Act
        result = users_session_utils.get_ip_address(mock_request)

        # Assert
        assert result == "unknown"


class TestParseUserAgent:
    """
    Test suite for parse_user_agent function.
    """

    def test_parse_user_agent_pc_chrome(self):
        """
        Test parsing Chrome on Windows user agent.
        """
        # Arrange
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

        # Act
        result = users_session_utils.parse_user_agent(user_agent)

        # Assert
        assert result.device_type == users_session_utils.DeviceType.PC
        assert "Windows" in result.operating_system
        assert "Chrome" in result.browser

    def test_parse_user_agent_mobile(self):
        """
        Test parsing mobile user agent.
        """
        # Arrange
        user_agent = (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Mobile/15E148 Safari/604.1"
        )

        # Act
        result = users_session_utils.parse_user_agent(user_agent)

        # Assert
        assert result.device_type == users_session_utils.DeviceType.MOBILE

    def test_parse_user_agent_tablet(self):
        """
        Test parsing tablet user agent.
        """
        # Arrange
        user_agent = (
            "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Mobile/15E148 Safari/604.1"
        )

        # Act
        result = users_session_utils.parse_user_agent(user_agent)

        # Assert
        assert result.device_type == users_session_utils.DeviceType.TABLET

    def test_parse_user_agent_empty(self):
        """
        Test parsing empty user agent.
        """
        # Arrange
        user_agent = ""

        # Act
        result = users_session_utils.parse_user_agent(user_agent)

        # Assert
        assert result.device_type == users_session_utils.DeviceType.PC
        assert result.operating_system == "Other"
        assert result.browser == "Other"


class TestCreateSessionObject:
    """
    Test suite for create_session_object function.
    """

    def test_create_session_object_success(self):
        """
        Test successful session object creation.
        """
        # Arrange
        session_id = "test-session-id"
        mock_user = MagicMock(spec=users_schema.UsersRead)
        mock_user.id = 1

        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda h, d=None: (
            "Mozilla/5.0 (Windows NT 10.0)" if h == "user-agent" else d
        )
        mock_request.client.host = "192.168.1.1"

        hashed_token = "hashed-refresh-token"
        exp = datetime.now(timezone.utc) + timedelta(days=7)

        # Act
        result = users_session_utils.create_session_object(
            session_id, mock_user, mock_request, hashed_token, exp
        )

        # Assert
        assert result.id == session_id
        assert result.user_id == 1
        assert result.refresh_token == hashed_token
        assert result.ip_address == "192.168.1.1"
        assert result.token_family_id == session_id
        assert result.rotation_count == 0
        assert result.tokens_exchanged is False

    def test_create_session_object_with_oauth_state(self):
        """
        Test session object creation with OAuth state.
        """
        # Arrange
        session_id = "test-session-id"
        mock_user = MagicMock(spec=users_schema.UsersRead)
        mock_user.id = 1

        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda h, d=None: (
            "Mozilla/5.0" if h == "user-agent" else d
        )
        mock_request.client.host = "192.168.1.1"

        hashed_token = "hashed-refresh-token"
        exp = datetime.now(timezone.utc) + timedelta(days=7)
        oauth_state_id = "oauth-state-123"

        # Act
        result = users_session_utils.create_session_object(
            session_id,
            mock_user,
            mock_request,
            hashed_token,
            exp,
            oauth_state_id=oauth_state_id,
        )

        # Assert
        assert result.oauth_state_id == oauth_state_id

    def test_create_session_object_with_csrf_hash(self):
        """
        Test session object creation with CSRF hash.
        """
        # Arrange
        session_id = "test-session-id"
        mock_user = MagicMock(spec=users_schema.UsersRead)
        mock_user.id = 1

        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda h, d=None: (
            "Mozilla/5.0" if h == "user-agent" else d
        )
        mock_request.client.host = "192.168.1.1"

        hashed_token = "hashed-refresh-token"
        exp = datetime.now(timezone.utc) + timedelta(days=7)
        csrf_hash = "csrf-token-hash"

        # Act
        result = users_session_utils.create_session_object(
            session_id,
            mock_user,
            mock_request,
            hashed_token,
            exp,
            csrf_token_hash=csrf_hash,
        )

        # Assert
        assert result.csrf_token_hash == csrf_hash


class TestEditSessionObject:
    """
    Test suite for edit_session_object function.
    """

    def test_edit_session_object_success(self):
        """
        Test successful session object edit.
        """
        # Arrange
        now = datetime.now(timezone.utc)
        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda h, d=None: (
            "Mozilla/5.0 (Windows NT 10.0)" if h == "user-agent" else d
        )
        mock_request.client.host = "192.168.1.2"

        existing_session = users_session_schema.UsersSessionsInternal(
            id="test-session-id",
            user_id=1,
            refresh_token="old-token",
            ip_address="192.168.1.1",
            device_type="PC",
            operating_system="Windows",
            operating_system_version="10",
            browser="Chrome",
            browser_version="120.0",
            created_at=now - timedelta(hours=1),
            last_activity_at=now - timedelta(minutes=30),
            expires_at=now + timedelta(days=6),
            token_family_id="family-id",
            rotation_count=0,
        )

        new_hashed_token = "new-hashed-token"
        new_exp = now + timedelta(days=7)

        # Act
        result = users_session_utils.edit_session_object(
            mock_request, new_hashed_token, new_exp, existing_session
        )

        # Assert
        assert result.id == existing_session.id
        assert result.user_id == existing_session.user_id
        assert result.refresh_token == new_hashed_token
        assert result.ip_address == "192.168.1.2"
        assert result.expires_at == new_exp
        assert result.rotation_count == 1
        assert result.token_family_id == existing_session.token_family_id

    def test_edit_session_object_increments_rotation(self):
        """
        Test that edit increments rotation count.
        """
        # Arrange
        now = datetime.now(timezone.utc)
        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda h, d=None: (
            "Mozilla/5.0" if h == "user-agent" else d
        )
        mock_request.client.host = "192.168.1.1"

        existing_session = users_session_schema.UsersSessionsInternal(
            id="test-session-id",
            user_id=1,
            refresh_token="old-token",
            ip_address="192.168.1.1",
            device_type="PC",
            operating_system="Windows",
            operating_system_version="10",
            browser="Chrome",
            browser_version="120.0",
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(days=7),
            token_family_id="family-id",
            rotation_count=5,
        )

        new_hashed_token = "new-hashed-token"
        new_exp = now + timedelta(days=7)

        # Act
        result = users_session_utils.edit_session_object(
            mock_request, new_hashed_token, new_exp, existing_session
        )

        # Assert
        assert result.rotation_count == 6


class TestCleanupIdleSessions:
    """
    Test suite for cleanup_idle_sessions function.
    """

    @patch(
        "users.users_sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_ENABLED", False
    )
    def test_cleanup_idle_sessions_disabled(self):
        """
        Test cleanup is skipped when disabled.
        """
        # Act & Assert (should not raise and should return early)
        users_session_utils.cleanup_idle_sessions()

    @patch(
        "users.users_sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_ENABLED", True
    )
    @patch("users.users_sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_HOURS", 24)
    @patch("users.users_sessions.utils.SessionLocal")
    @patch("users.users_sessions.utils.users_session_crud.delete_idle_sessions")
    def test_cleanup_idle_sessions_success(self, mock_delete_idle, mock_session_local):
        """
        Test successful cleanup of idle sessions.
        """
        # Arrange
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_delete_idle.return_value = 5

        # Act
        users_session_utils.cleanup_idle_sessions()

        # Assert
        mock_delete_idle.assert_called_once()

    @patch(
        "users.users_sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_ENABLED", True
    )
    @patch("users.users_sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_HOURS", 24)
    @patch("users.users_sessions.utils.SessionLocal")
    @patch("users.users_sessions.utils.users_session_crud.delete_idle_sessions")
    @patch("users.users_sessions.utils.core_logger.print_to_log")
    def test_cleanup_idle_sessions_error_handling(
        self, mock_logger, mock_delete_idle, mock_session_local
    ):
        """
        Test error handling in cleanup.
        """
        # Arrange
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_delete_idle.side_effect = Exception("Database error")

        # Act (should not raise)
        users_session_utils.cleanup_idle_sessions()

        # Assert
        mock_logger.assert_called()
