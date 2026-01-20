import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

import users.users_session.schema as users_session_schema


class TestUsersSessionsBaseSchema:
    """
    Test suite for UsersSessionsBase Pydantic schema.
    """

    def test_base_schema_valid_instance(self):
        """
        Test UsersSessionsBase schema with valid data.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act
        session = users_session_schema.UsersSessionsBase(
            id="test-session-id",
            ip_address="192.168.1.1",
            device_type="PC",
            operating_system="Windows",
            operating_system_version="10",
            browser="Chrome",
            browser_version="120.0",
            created_at=now,
            last_activity_at=now,
            expires_at=now,
        )

        # Assert
        assert session.id == "test-session-id"
        assert session.ip_address == "192.168.1.1"
        assert session.device_type == "PC"
        assert session.operating_system == "Windows"
        assert session.operating_system_version == "10"
        assert session.browser == "Chrome"
        assert session.browser_version == "120.0"
        assert session.created_at == now
        assert session.last_activity_at == now
        assert session.expires_at == now

    def test_base_schema_requires_id(self):
        """
        Test UsersSessionsBase schema requires id field.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            users_session_schema.UsersSessionsBase(
                ip_address="192.168.1.1",
                device_type="PC",
                operating_system="Windows",
                operating_system_version="10",
                browser="Chrome",
                browser_version="120.0",
                created_at=now,
                last_activity_at=now,
                expires_at=now,
            )

        assert "id" in str(exc_info.value)

    def test_base_schema_max_length_ip_address(self):
        """
        Test UsersSessionsBase schema ip_address max length validation.
        """
        # Arrange
        now = datetime.now(timezone.utc)
        long_ip = "a" * 50  # Exceeds 45 character limit

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            users_session_schema.UsersSessionsBase(
                id="test-session-id",
                ip_address=long_ip,
                device_type="PC",
                operating_system="Windows",
                operating_system_version="10",
                browser="Chrome",
                browser_version="120.0",
                created_at=now,
                last_activity_at=now,
                expires_at=now,
            )

        assert "ip_address" in str(exc_info.value)

    def test_base_schema_max_length_device_type(self):
        """
        Test UsersSessionsBase schema device_type max length validation.
        """
        # Arrange
        now = datetime.now(timezone.utc)
        long_device = "a" * 50  # Exceeds 45 character limit

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            users_session_schema.UsersSessionsBase(
                id="test-session-id",
                ip_address="192.168.1.1",
                device_type=long_device,
                operating_system="Windows",
                operating_system_version="10",
                browser="Chrome",
                browser_version="120.0",
                created_at=now,
                last_activity_at=now,
                expires_at=now,
            )

        assert "device_type" in str(exc_info.value)

    def test_base_schema_strict_string_validation(self):
        """
        Test UsersSessionsBase schema enforces strict string types.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            users_session_schema.UsersSessionsBase(
                id=12345,  # Should be string
                ip_address="192.168.1.1",
                device_type="PC",
                operating_system="Windows",
                operating_system_version="10",
                browser="Chrome",
                browser_version="120.0",
                created_at=now,
                last_activity_at=now,
                expires_at=now,
            )

        assert "id" in str(exc_info.value)

    def test_base_schema_from_attributes(self):
        """
        Test UsersSessionsBase schema has from_attributes config.
        """
        # Assert
        assert (
            users_session_schema.UsersSessionsBase.model_config.get("from_attributes")
            is True
        )


class TestUsersSessionsReadSchema:
    """
    Test suite for UsersSessionsRead Pydantic schema.
    """

    def test_read_schema_includes_user_id(self):
        """
        Test UsersSessionsRead schema includes user_id field.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act
        session = users_session_schema.UsersSessionsRead(
            id="test-session-id",
            ip_address="192.168.1.1",
            device_type="PC",
            operating_system="Windows",
            operating_system_version="10",
            browser="Chrome",
            browser_version="120.0",
            created_at=now,
            last_activity_at=now,
            expires_at=now,
            user_id=1,
        )

        # Assert
        assert session.user_id == 1

    def test_read_schema_requires_user_id(self):
        """
        Test UsersSessionsRead schema requires user_id field.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            users_session_schema.UsersSessionsRead(
                id="test-session-id",
                ip_address="192.168.1.1",
                device_type="PC",
                operating_system="Windows",
                operating_system_version="10",
                browser="Chrome",
                browser_version="120.0",
                created_at=now,
                last_activity_at=now,
                expires_at=now,
            )

        assert "user_id" in str(exc_info.value)

    def test_read_schema_user_id_positive(self):
        """
        Test UsersSessionsRead schema user_id must be >= 1.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            users_session_schema.UsersSessionsRead(
                id="test-session-id",
                ip_address="192.168.1.1",
                device_type="PC",
                operating_system="Windows",
                operating_system_version="10",
                browser="Chrome",
                browser_version="120.0",
                created_at=now,
                last_activity_at=now,
                expires_at=now,
                user_id=0,
            )

        assert "user_id" in str(exc_info.value)

    def test_read_schema_inherits_from_base(self):
        """
        Test UsersSessionsRead inherits from UsersSessionsBase.
        """
        # Assert
        assert issubclass(
            users_session_schema.UsersSessionsRead,
            users_session_schema.UsersSessionsBase,
        )


class TestUsersSessionsInternalSchema:
    """
    Test suite for UsersSessionsInternal Pydantic schema.
    """

    def test_internal_schema_includes_all_fields(self):
        """
        Test UsersSessionsInternal schema includes all fields.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act
        session = users_session_schema.UsersSessionsInternal(
            id="test-session-id",
            ip_address="192.168.1.1",
            device_type="PC",
            operating_system="Windows",
            operating_system_version="10",
            browser="Chrome",
            browser_version="120.0",
            created_at=now,
            last_activity_at=now,
            expires_at=now,
            user_id=1,
            refresh_token="hashed-token",
            oauth_state_id=None,
            tokens_exchanged=False,
            token_family_id="family-id",
            rotation_count=0,
            last_rotation_at=None,
            csrf_token_hash=None,
        )

        # Assert
        assert session.refresh_token == "hashed-token"
        assert session.oauth_state_id is None
        assert session.tokens_exchanged is False
        assert session.token_family_id == "family-id"
        assert session.rotation_count == 0
        assert session.last_rotation_at is None
        assert session.csrf_token_hash is None

    def test_internal_schema_requires_refresh_token(self):
        """
        Test UsersSessionsInternal schema requires refresh_token.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            users_session_schema.UsersSessionsInternal(
                id="test-session-id",
                ip_address="192.168.1.1",
                device_type="PC",
                operating_system="Windows",
                operating_system_version="10",
                browser="Chrome",
                browser_version="120.0",
                created_at=now,
                last_activity_at=now,
                expires_at=now,
                user_id=1,
                tokens_exchanged=False,
                token_family_id="family-id",
                rotation_count=0,
            )

        assert "refresh_token" in str(exc_info.value)

    def test_internal_schema_tokens_exchanged_default(self):
        """
        Test UsersSessionsInternal schema tokens_exchanged default.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act
        session = users_session_schema.UsersSessionsInternal(
            id="test-session-id",
            ip_address="192.168.1.1",
            device_type="PC",
            operating_system="Windows",
            operating_system_version="10",
            browser="Chrome",
            browser_version="120.0",
            created_at=now,
            last_activity_at=now,
            expires_at=now,
            user_id=1,
            refresh_token="hashed-token",
            token_family_id="family-id",
            rotation_count=0,
        )

        # Assert
        assert session.tokens_exchanged is False

    def test_internal_schema_rotation_count_non_negative(self):
        """
        Test UsersSessionsInternal schema rotation_count must be >= 0.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            users_session_schema.UsersSessionsInternal(
                id="test-session-id",
                ip_address="192.168.1.1",
                device_type="PC",
                operating_system="Windows",
                operating_system_version="10",
                browser="Chrome",
                browser_version="120.0",
                created_at=now,
                last_activity_at=now,
                expires_at=now,
                user_id=1,
                refresh_token="hashed-token",
                token_family_id="family-id",
                rotation_count=-1,
            )

        assert "rotation_count" in str(exc_info.value)

    def test_internal_schema_oauth_state_id_max_length(self):
        """
        Test UsersSessionsInternal schema oauth_state_id max length.
        """
        # Arrange
        now = datetime.now(timezone.utc)
        long_oauth_state = "a" * 70  # Exceeds 64 character limit

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            users_session_schema.UsersSessionsInternal(
                id="test-session-id",
                ip_address="192.168.1.1",
                device_type="PC",
                operating_system="Windows",
                operating_system_version="10",
                browser="Chrome",
                browser_version="120.0",
                created_at=now,
                last_activity_at=now,
                expires_at=now,
                user_id=1,
                refresh_token="hashed-token",
                oauth_state_id=long_oauth_state,
                token_family_id="family-id",
                rotation_count=0,
            )

        assert "oauth_state_id" in str(exc_info.value)

    def test_internal_schema_inherits_from_base(self):
        """
        Test UsersSessionsInternal inherits from UsersSessionsBase.
        """
        # Assert
        assert issubclass(
            users_session_schema.UsersSessionsInternal,
            users_session_schema.UsersSessionsBase,
        )

    def test_internal_schema_with_all_optional_fields(self):
        """
        Test UsersSessionsInternal schema with all optional fields set.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act
        session = users_session_schema.UsersSessionsInternal(
            id="test-session-id",
            ip_address="192.168.1.1",
            device_type="PC",
            operating_system="Windows",
            operating_system_version="10",
            browser="Chrome",
            browser_version="120.0",
            created_at=now,
            last_activity_at=now,
            expires_at=now,
            user_id=1,
            refresh_token="hashed-token",
            oauth_state_id="oauth-state-123",
            tokens_exchanged=True,
            token_family_id="family-id",
            rotation_count=5,
            last_rotation_at=now,
            csrf_token_hash="csrf-hash",
        )

        # Assert
        assert session.oauth_state_id == "oauth-state-123"
        assert session.tokens_exchanged is True
        assert session.rotation_count == 5
        assert session.last_rotation_at == now
        assert session.csrf_token_hash == "csrf-hash"
