"""Tests for users_api_keys Pydantic schemas."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

import modules.auth.api_keys.schema as users_api_keys_schema


class TestUsersApiKeyCreate:
    """
    Test suite for UsersApiKeyCreate schema.
    """

    def test_create_valid_minimal(self):
        """Test valid key creation with required fields only."""
        data = users_api_keys_schema.UsersApiKeyCreate(
            name="FitoTrack",
            scopes=["activities:upload"],
        )
        assert data.name == "FitoTrack"
        assert data.scopes == ["activities:upload"]
        assert data.expires_at is None

    def test_create_with_expiry(self):
        """Test valid key creation with an expiration date."""
        expires = datetime.now(UTC) + timedelta(days=30)
        data = users_api_keys_schema.UsersApiKeyCreate(
            name="Expiring Key",
            scopes=["activities:upload"],
            expires_at=expires,
        )
        assert data.expires_at == expires

    def test_create_name_empty_fails(self):
        """Test that an empty name fails validation (min_length=1)."""
        with pytest.raises(ValidationError):
            users_api_keys_schema.UsersApiKeyCreate(
                name="",
                scopes=["activities:upload"],
            )

    def test_create_name_too_long_fails(self):
        """Test that a name exceeding 100 characters fails validation."""
        with pytest.raises(ValidationError):
            users_api_keys_schema.UsersApiKeyCreate(
                name="x" * 101,
                scopes=["activities:upload"],
            )

    def test_create_name_exactly_100_chars(self):
        """Test that a name of exactly 100 characters is valid."""
        data = users_api_keys_schema.UsersApiKeyCreate(
            name="x" * 100,
            scopes=["activities:upload"],
        )
        assert len(data.name) == 100

    def test_create_scopes_empty_list_fails(self):
        """Test that an empty scopes list fails validation (min_length=1)."""
        with pytest.raises(ValidationError):
            users_api_keys_schema.UsersApiKeyCreate(
                name="Test Key",
                scopes=[],
            )

    def test_create_unknown_scope_fails(self):
        """Test that an unsupported scope string raises a ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            users_api_keys_schema.UsersApiKeyCreate(
                name="Test Key",
                scopes=["totally:invalid_scope"],
            )
        assert "Unsupported API key scopes" in str(exc_info.value)

    def test_create_profile_scope_fails(self):
        """Test that JWT-only scopes are rejected for API keys."""
        with pytest.raises(ValidationError) as exc_info:
            users_api_keys_schema.UsersApiKeyCreate(
                name="Profile Key",
                scopes=["profile"],
            )
        assert "Unsupported API key scopes" in str(exc_info.value)

    def test_create_multiple_scopes_with_unsupported_fails(self):
        """Test that only activities:upload is accepted for API keys."""
        with pytest.raises(ValidationError) as exc_info:
            users_api_keys_schema.UsersApiKeyCreate(
                name="Multi-scope Key",
                scopes=["activities:read", "activities:upload", "gears:read"],
            )
        assert "Unsupported API key scopes" in str(exc_info.value)

    def test_create_partial_invalid_scope_fails(self):
        """Test that a mix of valid and invalid scopes fails validation."""
        with pytest.raises(ValidationError):
            users_api_keys_schema.UsersApiKeyCreate(
                name="Mixed Key",
                scopes=["activities:upload", "fake:scope"],
            )

    def test_create_unsupported_scope_message_names_scopes_without_set_repr(self):
        """The error lists the scope names, not the Python repr of a set."""
        with pytest.raises(ValidationError) as exc_info:
            users_api_keys_schema.UsersApiKeyCreate(name="Test Key", scopes=["bogus:scope"])
        message = str(exc_info.value)
        assert "bogus:scope" in message
        assert "activities:upload" in message
        assert "frozenset" not in message

    def test_create_past_expiry_fails(self):
        """An expiry that has already passed is refused."""
        with pytest.raises(ValidationError, match="expires_at"):
            users_api_keys_schema.UsersApiKeyCreate(
                name="Test Key",
                scopes=["activities:upload"],
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )

    def test_create_past_naive_expiry_fails(self):
        """A naive expiry is read as UTC, so a past one is refused."""
        with pytest.raises(ValidationError, match="expires_at"):
            users_api_keys_schema.UsersApiKeyCreate(
                name="Test Key",
                scopes=["activities:upload"],
                expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
            )

    def test_create_future_naive_expiry_is_read_as_utc(self):
        """A naive future expiry is accepted and stored as UTC-aware."""
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1)
        data = users_api_keys_schema.UsersApiKeyCreate(
            name="Test Key", scopes=["activities:upload"], expires_at=expires
        )
        assert data.expires_at == expires.replace(tzinfo=UTC)

    def test_create_future_date_only_expiry_is_accepted(self):
        """The date-only value the frontend sends is accepted."""
        day = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
        data = users_api_keys_schema.UsersApiKeyCreate.model_validate(
            {"name": "Test Key", "scopes": ["activities:upload"], "expires_at": day}
        )
        assert data.expires_at is not None
        assert data.expires_at.date().isoformat() == day


class TestUsersApiKeyRead:
    """
    Test suite for UsersApiKeyRead schema.
    """

    def test_read_schema_valid(self):
        """Test UsersApiKeyRead instantiation with all fields."""
        now = datetime.now(UTC)
        data = users_api_keys_schema.UsersApiKeyRead(
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
        read = users_api_keys_schema.UsersApiKeyRead(
            id="some-uuid",
            user_id=1,
            name="My Key",
            key_prefix="abcdefgh",
            scopes='["activities:upload"]',
            expires_at=datetime.now(UTC) + timedelta(days=30),
            created_at=datetime.now(UTC),
            is_active=True,
        )
        created = users_api_keys_schema.UsersApiKeyCreatedRead(**read.model_dump(), key="endurain_x")
        assert created.scopes == ["activities:upload"]

    def test_read_schema_no_key_field(self):
        """Test that UsersApiKeyRead does not expose a 'key' field."""
        assert not hasattr(users_api_keys_schema.UsersApiKeyRead, "key")

    def test_read_schema_user_id_ge_1_fails(self):
        """Test that user_id < 1 fails validation."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            users_api_keys_schema.UsersApiKeyRead(
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
        """Test that UsersApiKeyRead has from_attributes=True (ORM mode)."""
        assert users_api_keys_schema.UsersApiKeyRead.model_config.get("from_attributes") is True


class TestUsersApiKeyCreated:
    """
    Test suite for UsersApiKeyCreatedRead schema.
    """

    def test_created_schema_has_key_field(self):
        """Test that UsersApiKeyCreatedRead includes the raw 'key' field."""
        now = datetime.now(UTC)
        data = users_api_keys_schema.UsersApiKeyCreatedRead(
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
        """Test that extra fields are forbidden on UsersApiKeyCreatedRead."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            users_api_keys_schema.UsersApiKeyCreatedRead(
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
        """Test that UsersApiKeyCreatedRead has from_attributes=True (ORM mode)."""
        assert users_api_keys_schema.UsersApiKeyCreatedRead.model_config.get("from_attributes") is True
