"""Tests for users_api_keys Pydantic schemas."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

import modules.auth.api_keys.schema as users_api_keys_schema


class TestUsersApiKeyCreate:
    """
    Test suite for UserApiKeyCreate schema.
    """

    def test_create_valid_minimal(self):
        """Test valid key creation with required fields only."""
        data = users_api_keys_schema.UserApiKeyCreate(
            step_up={"current_password": "pw"},
            name="FitoTrack",
            scopes=["activities:upload"],
        )
        assert data.name == "FitoTrack"
        assert data.scopes == ["activities:upload"]
        assert data.expires_at is None

    def test_create_with_expiry(self):
        """Test valid key creation with an expiration date."""
        expires = datetime.now(UTC) + timedelta(days=30)
        data = users_api_keys_schema.UserApiKeyCreate(
            step_up={"current_password": "pw"},
            name="Expiring Key",
            scopes=["activities:upload"],
            expires_at=expires,
        )
        assert data.expires_at == expires

    def test_create_name_empty_fails(self):
        """Test that an empty name fails validation (min_length=1)."""
        with pytest.raises(ValidationError):
            users_api_keys_schema.UserApiKeyCreate(
                step_up={"current_password": "pw"},
                name="",
                scopes=["activities:upload"],
            )

    def test_create_name_too_long_fails(self):
        """Test that a name exceeding 100 characters fails validation."""
        with pytest.raises(ValidationError):
            users_api_keys_schema.UserApiKeyCreate(
                step_up={"current_password": "pw"},
                name="x" * 101,
                scopes=["activities:upload"],
            )

    def test_create_name_exactly_100_chars(self):
        """Test that a name of exactly 100 characters is valid."""
        data = users_api_keys_schema.UserApiKeyCreate(
            step_up={"current_password": "pw"},
            name="x" * 100,
            scopes=["activities:upload"],
        )
        assert len(data.name) == 100

    def test_create_scopes_empty_list_fails(self):
        """Test that an empty scopes list fails validation (min_length=1)."""
        with pytest.raises(ValidationError):
            users_api_keys_schema.UserApiKeyCreate(
                step_up={"current_password": "pw"},
                name="Test Key",
                scopes=[],
            )

    def test_create_unknown_scope_fails(self):
        """Test that an unsupported scope string raises a ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            users_api_keys_schema.UserApiKeyCreate(
                step_up={"current_password": "pw"},
                name="Test Key",
                scopes=["totally:invalid_scope"],
            )
        assert "Unsupported API key scopes" in str(exc_info.value)

    def test_create_profile_scope_fails(self):
        """Test that JWT-only scopes are rejected for API keys."""
        with pytest.raises(ValidationError) as exc_info:
            users_api_keys_schema.UserApiKeyCreate(
                step_up={"current_password": "pw"},
                name="Profile Key",
                scopes=["profile"],
            )
        assert "Unsupported API key scopes" in str(exc_info.value)

    def test_create_multiple_scopes_with_unsupported_fails(self):
        """Test that only activities:upload is accepted for API keys."""
        with pytest.raises(ValidationError) as exc_info:
            users_api_keys_schema.UserApiKeyCreate(
                step_up={"current_password": "pw"},
                name="Multi-scope Key",
                scopes=["activities:read", "activities:upload", "gears:read"],
            )
        assert "Unsupported API key scopes" in str(exc_info.value)

    def test_create_partial_invalid_scope_fails(self):
        """Test that a mix of valid and invalid scopes fails validation."""
        with pytest.raises(ValidationError):
            users_api_keys_schema.UserApiKeyCreate(
                step_up={"current_password": "pw"},
                name="Mixed Key",
                scopes=["activities:upload", "fake:scope"],
            )

    def test_create_unsupported_scope_message_names_scopes_without_set_repr(self):
        """The error lists the scope names, not the Python repr of a set."""
        with pytest.raises(ValidationError) as exc_info:
            users_api_keys_schema.UserApiKeyCreate(
                step_up={"current_password": "pw"}, name="Test Key", scopes=["bogus:scope"]
            )
        message = str(exc_info.value)
        assert "bogus:scope" in message
        assert "activities:upload" in message
        assert "frozenset" not in message

    def test_create_past_expiry_fails(self):
        """An expiry that has already passed is refused."""
        with pytest.raises(ValidationError, match="expires_at"):
            users_api_keys_schema.UserApiKeyCreate(
                step_up={"current_password": "pw"},
                name="Test Key",
                scopes=["activities:upload"],
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )

    def test_create_naive_expiry_is_refused(self):
        """An expiry without a UTC offset is refused."""
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1)
        with pytest.raises(ValidationError, match="expires_at"):
            users_api_keys_schema.UserApiKeyCreate(
                step_up={"current_password": "pw"}, name="Test Key", scopes=["activities:upload"], expires_at=expires
            )

    def test_create_date_only_expiry_is_refused(self):
        """A bare date has no offset, so it is refused."""
        day = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
        with pytest.raises(ValidationError, match="expires_at"):
            users_api_keys_schema.UserApiKeyCreate.model_validate(
                {"name": "Test Key", "scopes": ["activities:upload"], "expires_at": day}
            )

    def test_create_future_offset_expiry_is_stored_in_utc(self):
        """An expiry with an offset is accepted and kept in UTC."""
        expires = (datetime.now(UTC) + timedelta(days=1)).astimezone(timezone(timedelta(hours=2)))
        data = users_api_keys_schema.UserApiKeyCreate(
            step_up={"current_password": "pw"}, name="Test Key", scopes=["activities:upload"], expires_at=expires
        )
        assert data.expires_at == expires
        assert data.expires_at is not None
        assert data.expires_at.utcoffset() == timedelta(0)


class TestUsersApiKeyRead:
    """
    Test suite for UserApiKeyRead schema.
    """

    def test_read_schema_valid(self):
        """Test UserApiKeyRead instantiation with all fields."""
        now = datetime.now(UTC)
        data = users_api_keys_schema.UserApiKeyRead(
            id="some-uuid",
            user_id=1,
            name="My Key",
            key_prefix="abcdefgh",
            scopes='["activities:upload"]',
            expires_at=now + timedelta(days=30),
            last_used_at=None,
            created_at=now,
            is_active=True,
        )
        assert data.id == "some-uuid"
        assert data.user_id == 1
        assert data.is_active is True
        assert data.scopes == ["activities:upload"]

    def test_read_schema_scopes_survive_a_created_read_round_trip(self):
        """The scopes stay a list when a read dump builds the creation response."""
        read = users_api_keys_schema.UserApiKeyRead(
            id="some-uuid",
            user_id=1,
            name="My Key",
            key_prefix="abcdefgh",
            scopes='["activities:upload"]',
            expires_at=datetime.now(UTC) + timedelta(days=30),
            created_at=datetime.now(UTC),
            is_active=True,
        )
        created = users_api_keys_schema.UserApiKeyCreatedRead(**read.model_dump(), key="endurain_x")
        assert created.scopes == ["activities:upload"]

    def test_read_schema_no_key_field(self):
        """Test that UserApiKeyRead does not expose a 'key' field."""
        assert not hasattr(users_api_keys_schema.UserApiKeyRead, "key")

    def test_read_schema_user_id_ge_1_fails(self):
        """Test that user_id < 1 fails validation."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            users_api_keys_schema.UserApiKeyRead(
                id="some-uuid",
                user_id=0,
                name="My Key",
                key_prefix="abcdefgh",
                scopes='["activities:upload"]',
                expires_at=now + timedelta(days=30),
                last_used_at=None,
                created_at=now,
                is_active=True,
            )

    def test_read_schema_from_attributes(self):
        """Test that UserApiKeyRead has from_attributes=True (ORM mode)."""
        assert users_api_keys_schema.UserApiKeyRead.model_config.get("from_attributes") is True


class TestUsersApiKeyCreated:
    """
    Test suite for UserApiKeyCreatedRead schema.
    """

    def test_created_schema_has_key_field(self):
        """Test that UserApiKeyCreatedRead includes the raw 'key' field."""
        now = datetime.now(UTC)
        data = users_api_keys_schema.UserApiKeyCreatedRead(
            id="some-uuid",
            user_id=1,
            name="My Key",
            key_prefix="abcdefgh",
            scopes='["activities:upload"]',
            expires_at=now + timedelta(days=30),
            last_used_at=None,
            created_at=now,
            is_active=True,
            key="endurain_secrettoken",
        )
        assert data.key == "endurain_secrettoken"

    def test_created_schema_extra_forbid(self):
        """Test that extra fields are forbidden on UserApiKeyCreatedRead."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            users_api_keys_schema.UserApiKeyCreatedRead(
                id="some-uuid",
                user_id=1,
                name="My Key",
                key_prefix="abcdefgh",
                scopes='["activities:upload"]',
                expires_at=now + timedelta(days=30),
                last_used_at=None,
                created_at=now,
                is_active=True,
                key="endurain_secrettoken",
                unexpected_field="bad",
            )

    def test_created_schema_from_attributes(self):
        """Test that UserApiKeyCreatedRead has from_attributes=True (ORM mode)."""
        assert users_api_keys_schema.UserApiKeyCreatedRead.model_config.get("from_attributes") is True
