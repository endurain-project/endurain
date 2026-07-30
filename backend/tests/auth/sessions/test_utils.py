import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import core.network as core_network
import modules.auth.sessions.models as users_session_models
import modules.auth.sessions.schema as users_session_schema
import modules.auth.sessions.utils as _auth_sessions_utils
import modules.auth.sessions.utils as users_session_utils
import modules.users.users.schema as users_schema


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

    @patch("modules.auth.sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_ENABLED", True)
    @patch("modules.auth.sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_HOURS", 1)
    @patch("modules.auth.sessions.utils.auth_constants.SESSION_ABSOLUTE_TIMEOUT_HOURS", 24)
    def test_validate_session_timeout_valid(self):
        """
        Test valid session passes timeout validation.
        """
        # Arrange
        now = datetime.now(UTC)
        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_session.last_activity_at = now - timedelta(minutes=30)
        mock_session.created_at = now - timedelta(hours=12)

        # Act & Assert (should not raise)
        users_session_utils.validate_session_timeout(mock_session)

    @patch("modules.auth.sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_ENABLED", True)
    @patch("modules.auth.sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_HOURS", 1)
    @patch("modules.auth.sessions.utils.auth_constants.SESSION_ABSOLUTE_TIMEOUT_HOURS", 24)
    def test_validate_session_timeout_idle_expired(self):
        """
        Test session with idle timeout raises exception.
        """
        # Arrange
        now = datetime.now(UTC)
        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_session.last_activity_at = now - timedelta(hours=2)
        mock_session.created_at = now - timedelta(hours=12)

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            users_session_utils.validate_session_timeout(mock_session)

        assert exc_info.value.status_code == 401
        assert "inactivity" in exc_info.value.detail

    @patch("modules.auth.sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_ENABLED", True)
    @patch("modules.auth.sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_HOURS", 1)
    @patch("modules.auth.sessions.utils.auth_constants.SESSION_ABSOLUTE_TIMEOUT_HOURS", 24)
    def test_validate_session_timeout_absolute_expired(self):
        """
        Test session with absolute timeout raises exception.
        """
        # Arrange
        now = datetime.now(UTC)
        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_session.last_activity_at = now - timedelta(minutes=30)
        mock_session.created_at = now - timedelta(hours=30)

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            users_session_utils.validate_session_timeout(mock_session)

        assert exc_info.value.status_code == 401
        assert "security" in exc_info.value.detail.lower()

    @patch("modules.auth.sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_ENABLED", False)
    def test_validate_session_timeout_disabled(self):
        """
        Test timeout validation is skipped when disabled.
        """
        # Arrange
        now = datetime.now(UTC)
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
    Test suite for core_network.get_ip_address.

    Tests are retargeted from the stale
    ``users_session_utils.get_ip_address`` alias (which no
    longer exists) to the canonical
    ``core.network.get_ip_address`` implementation that the
    session utilities call internally.
    """

    def test_get_ip_address_from_forwarded_for(self):
        """
        Test extracting IP from X-Forwarded-For when peer
        is trusted (TRUSTED_PROXIES = ["*"]).
        """
        # Arrange
        mock_request = MagicMock()
        mock_request.client.host = "10.0.0.1"
        mock_request.headers.get.side_effect = lambda h: "192.168.1.1, 10.0.0.1" if h == "X-Forwarded-For" else None

        with patch.object(
            core_network.core_config.settings,
            "TRUSTED_PROXIES",
            ["*"],
        ):
            # Act
            result = core_network.get_ip_address(mock_request)

        # Assert
        assert result == "192.168.1.1"

    def test_get_ip_address_from_real_ip(self):
        """
        Test extracting IP from X-Real-IP when
        X-Forwarded-For absent and peer is trusted.
        """
        # Arrange
        mock_request = MagicMock()
        mock_request.client.host = "10.0.0.1"
        mock_request.headers.get.side_effect = lambda h: "172.16.0.5" if h == "X-Real-IP" else None

        with patch.object(
            core_network.core_config.settings,
            "TRUSTED_PROXIES",
            ["*"],
        ):
            # Act
            result = core_network.get_ip_address(mock_request)

        # Assert
        assert result == "172.16.0.5"

    def test_get_ip_address_from_client(self):
        """
        Test that direct peer IP is returned when no
        forwarded headers are present.
        """
        # Arrange
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers.get.return_value = None

        with patch.object(
            core_network.core_config.settings,
            "TRUSTED_PROXIES",
            ["*"],
        ):
            # Act
            result = core_network.get_ip_address(mock_request)

        # Assert
        assert result == "127.0.0.1"

    def test_get_ip_address_no_client(self):
        """
        Test that "unknown" is returned when request has
        no client info.
        """
        # Arrange
        mock_request = MagicMock()
        mock_request.client = None
        mock_request.headers.get.return_value = None

        # Act
        result = core_network.get_ip_address(mock_request)

        # Assert
        assert result == "unknown"

    def test_create_session_object_propagates_ip_from_core_network(
        self,
    ):
        """
        Test IP address from core_network is stored in the
        session object built by create_session_object.
        """
        # Arrange
        session_id = "test-session-id"
        mock_user = MagicMock(spec=users_schema.UsersRead)
        mock_user.id = 1
        mock_request = MagicMock()
        mock_request.client.host = "203.0.113.5"
        mock_request.headers.get.side_effect = lambda h, d=None: "Mozilla/5.0" if h == "user-agent" else None

        exp = datetime.now(UTC) + timedelta(days=7)

        with patch.object(
            core_network.core_config.settings,
            "TRUSTED_PROXIES",
            ["*"],
        ):
            # Act
            result = users_session_utils.create_session_object(
                session_id,
                mock_user,
                mock_request,
                "hashed-token",
                exp,
            )

        # Assert
        assert result.ip_address == "203.0.113.5"


class TestVerifyCsrfToken:
    """
    Test suite for verify_csrf_token and _hash_csrf_token utilities.
    """

    @patch(
        "modules.auth.sessions.utils.auth_constants.JWT_SECRET_KEY",
        "test-secret-key",
    )
    def test_verify_csrf_token_valid_returns_true(self):
        """
        Test verify_csrf_token returns True when the candidate
        token matches the stored HMAC-SHA256 digest.
        """
        # Arrange
        token = "csrf-plaintext-value"
        stored_hmac = hmac.new(
            b"test-secret-key",
            token.encode(),
            hashlib.sha256,
        ).hexdigest()

        # Act
        result = users_session_utils.verify_csrf_token(token, stored_hmac)

        # Assert
        assert result is True

    @patch(
        "modules.auth.sessions.utils.auth_constants.JWT_SECRET_KEY",
        "test-secret-key",
    )
    def test_verify_csrf_token_wrong_candidate_returns_false(self):
        """
        Test verify_csrf_token returns False when the candidate
        does not match the stored HMAC.
        """
        # Arrange
        real_token = "correct-csrf-token"
        stored_hmac = hmac.new(
            b"test-secret-key",
            real_token.encode(),
            hashlib.sha256,
        ).hexdigest()
        wrong_candidate = "tampered-csrf-token"

        # Act
        result = users_session_utils.verify_csrf_token(wrong_candidate, stored_hmac)

        # Assert
        assert result is False

    @patch(
        "modules.auth.sessions.utils.auth_constants.JWT_SECRET_KEY",
        "test-secret-key",
    )
    def test_hash_csrf_token_deterministic(self):
        """
        Test _hash_csrf_token produces the same digest for
        identical inputs (deterministic HMAC).
        """
        # Arrange
        token = "some-csrf-token"

        # Act
        digest1 = _auth_sessions_utils._hash_csrf_token(token)
        digest2 = _auth_sessions_utils._hash_csrf_token(token)

        # Assert
        assert digest1 == digest2
        assert len(digest1) == 64  # SHA-256 hex = 64 chars

    @patch(
        "modules.auth.sessions.utils.auth_constants.JWT_SECRET_KEY",
        "key-a",
    )
    def test_hash_csrf_token_different_keys_produce_different_digests(
        self,
    ):
        """
        Test that different JWT_SECRET_KEY values produce
        different HMAC digests for the same token.
        """
        # Arrange
        token = "shared-token"
        digest_key_a = _auth_sessions_utils._hash_csrf_token(token)

        with patch(
            "modules.auth.sessions.utils.auth_constants.JWT_SECRET_KEY",
            "key-b",
        ):
            digest_key_b = _auth_sessions_utils._hash_csrf_token(token)

        # Assert
        assert digest_key_a != digest_key_b


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
        exp = datetime.now(UTC) + timedelta(days=7)

        # Act
        result = users_session_utils.create_session_object(session_id, mock_user, mock_request, hashed_token, exp)

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
        mock_request.headers.get.side_effect = lambda h, d=None: "Mozilla/5.0" if h == "user-agent" else d
        mock_request.client.host = "192.168.1.1"

        hashed_token = "hashed-refresh-token"
        exp = datetime.now(UTC) + timedelta(days=7)
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
        mock_request.headers.get.side_effect = lambda h, d=None: "Mozilla/5.0" if h == "user-agent" else d
        mock_request.client.host = "192.168.1.1"

        hashed_token = "hashed-refresh-token"
        exp = datetime.now(UTC) + timedelta(days=7)
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
        now = datetime.now(UTC)
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
        result = users_session_utils.edit_session_object(mock_request, new_hashed_token, new_exp, existing_session)

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
        now = datetime.now(UTC)
        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda h, d=None: "Mozilla/5.0" if h == "user-agent" else d
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
        result = users_session_utils.edit_session_object(mock_request, new_hashed_token, new_exp, existing_session)

        # Assert
        assert result.rotation_count == 6


class TestCleanupIdleSessions:
    """
    Test suite for cleanup_idle_sessions function.
    """

    @patch("modules.auth.sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_ENABLED", False)
    def test_cleanup_idle_sessions_disabled(self):
        """
        Test cleanup is skipped when disabled.
        """
        # Act & Assert (should not raise and should return early)
        users_session_utils.cleanup_idle_sessions()

    @patch("modules.auth.sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_ENABLED", True)
    @patch("modules.auth.sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_HOURS", 24)
    @patch("modules.auth.sessions.utils.SessionLocal")
    @patch("modules.auth.sessions.utils.auth_sessions_crud.delete_idle_sessions")
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

    @patch("modules.auth.sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_ENABLED", True)
    @patch("modules.auth.sessions.utils.auth_constants.SESSION_IDLE_TIMEOUT_HOURS", 24)
    @patch("modules.auth.sessions.utils.SessionLocal")
    @patch("modules.auth.sessions.utils.auth_sessions_crud.delete_idle_sessions")
    @patch("modules.auth.sessions.utils.core_logger.print_to_log")
    def test_cleanup_idle_sessions_error_handling(self, mock_logger, mock_delete_idle, mock_session_local):
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


_TEST_SECRET = "test-secret-key-for-testing-purposes-minimum-32-characters-long"


class TestCreateSessionUtilsCsrf:
    """
    Test suite verifying CSRF-token hashing inside the
    util-layer create_session function.
    """

    @patch(
        "modules.auth.sessions.utils.auth_constants.JWT_SECRET_KEY",
        _TEST_SECRET,
    )
    @patch("modules.auth.sessions.utils.auth_sessions_crud.create_session")
    def test_create_session_hashes_csrf_token_before_persistence(self, mock_crud_create, mock_db):
        """
        Test that create_session computes an HMAC-SHA256 of the
        plain csrf_token and passes the digest (not the plain
        value) to the CRUD layer.
        """
        # Arrange
        session_id = "sess-csrf-test"
        mock_user = MagicMock(spec=users_schema.UsersRead)
        mock_user.id = 42
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers.get.side_effect = lambda h, d=None: "Mozilla/5.0" if h == "user-agent" else d
        mock_hasher = MagicMock()
        mock_hasher.hash_password.return_value = "hashed-rt"
        csrf_token = "plain-csrf-token-value"
        expected_hash = hmac.new(
            _TEST_SECRET.encode(),
            csrf_token.encode(),
            hashlib.sha256,
        ).hexdigest()

        # Act
        users_session_utils.create_session(
            session_id,
            mock_user,
            mock_request,
            "refresh-token",
            mock_hasher,
            mock_db,
            csrf_token=csrf_token,
        )

        # Assert — CRUD was called with the hashed value
        mock_crud_create.assert_called_once()
        persisted_session = mock_crud_create.call_args[0][0]
        assert persisted_session.csrf_token_hash == expected_hash

    @patch(
        "modules.auth.sessions.utils.auth_constants.JWT_SECRET_KEY",
        _TEST_SECRET,
    )
    @patch("modules.auth.sessions.utils.auth_sessions_crud.create_session")
    def test_create_session_none_csrf_token_stores_none(self, mock_crud_create, mock_db):
        """
        Test that create_session stores None for csrf_token_hash
        when no csrf_token is provided.
        """
        # Arrange
        mock_user = MagicMock(spec=users_schema.UsersRead)
        mock_user.id = 1
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers.get.side_effect = lambda h, d=None: "Mozilla/5.0" if h == "user-agent" else d
        mock_hasher = MagicMock()
        mock_hasher.hash_password.return_value = "hashed-rt"

        # Act
        users_session_utils.create_session(
            "sess-no-csrf",
            mock_user,
            mock_request,
            "refresh-token",
            mock_hasher,
            mock_db,
        )

        # Assert
        persisted_session = mock_crud_create.call_args[0][0]
        assert persisted_session.csrf_token_hash is None


class TestEditSessionUtilsCsrf:
    """
    Test suite verifying CSRF-token hashing inside the
    util-layer edit_session function.
    """

    @patch(
        "modules.auth.sessions.utils.auth_constants.JWT_SECRET_KEY",
        _TEST_SECRET,
    )
    @patch("modules.auth.sessions.utils.auth_sessions_crud.edit_session")
    def test_edit_session_hashes_new_csrf_token_before_persistence(self, mock_crud_edit, mock_db):
        """
        Test that edit_session computes an HMAC-SHA256 of the
        plain new_csrf_token and passes the digest to the CRUD
        layer rather than the plain value.
        """
        # Arrange
        now = datetime.now(UTC)
        existing_session = users_session_schema.UsersSessionsInternal(
            id="sess-edit-csrf",
            user_id=1,
            refresh_token="old-token",
            ip_address="127.0.0.1",
            device_type="PC",
            operating_system="Linux",
            operating_system_version="5.15",
            browser="Firefox",
            browser_version="120.0",
            created_at=now - timedelta(hours=1),
            last_activity_at=now - timedelta(minutes=5),
            expires_at=now + timedelta(days=6),
            token_family_id="family-edit",
            rotation_count=0,
        )
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers.get.side_effect = lambda h, d=None: "Mozilla/5.0" if h == "user-agent" else d
        mock_hasher = MagicMock()
        mock_hasher.hash_password.return_value = "new-hashed-rt"
        new_csrf_token = "new-plain-csrf-token"
        expected_hash = hmac.new(
            _TEST_SECRET.encode(),
            new_csrf_token.encode(),
            hashlib.sha256,
        ).hexdigest()

        # Act
        users_session_utils.edit_session(
            existing_session,
            mock_request,
            "new-refresh-token",
            mock_hasher,
            mock_db,
            new_csrf_token=new_csrf_token,
        )

        # Assert — CRUD was called with the hashed value
        mock_crud_edit.assert_called_once()
        updated_session = mock_crud_edit.call_args[0][0]
        assert updated_session.csrf_token_hash == expected_hash

    @patch(
        "modules.auth.sessions.utils.auth_constants.JWT_SECRET_KEY",
        _TEST_SECRET,
    )
    @patch("modules.auth.sessions.utils.auth_sessions_crud.edit_session")
    def test_edit_session_none_csrf_token_stores_none(self, mock_crud_edit, mock_db):
        """
        Test that edit_session stores None for csrf_token_hash
        when no new_csrf_token is supplied.
        """
        # Arrange
        now = datetime.now(UTC)
        existing_session = users_session_schema.UsersSessionsInternal(
            id="sess-edit-no-csrf",
            user_id=1,
            refresh_token="old-token",
            ip_address="127.0.0.1",
            device_type="PC",
            operating_system="Linux",
            operating_system_version="5.15",
            browser="Firefox",
            browser_version="120.0",
            created_at=now - timedelta(hours=1),
            last_activity_at=now - timedelta(minutes=5),
            expires_at=now + timedelta(days=6),
            token_family_id="family-edit-no-csrf",
            rotation_count=0,
        )
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers.get.side_effect = lambda h, d=None: "Mozilla/5.0" if h == "user-agent" else d
        mock_hasher = MagicMock()
        mock_hasher.hash_password.return_value = "new-hashed-rt"

        # Act
        users_session_utils.edit_session(
            existing_session,
            mock_request,
            "new-refresh-token",
            mock_hasher,
            mock_db,
        )

        # Assert
        updated_session = mock_crud_edit.call_args[0][0]
        assert updated_session.csrf_token_hash is None
