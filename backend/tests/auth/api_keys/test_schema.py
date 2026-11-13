"""Tests for users_api_keys Pydantic schemas."""

import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

import modules.auth.api_keys.schema as users_api_keys_schema
import modules.auth.constants as auth_constants
from tests._helpers.auth import MOCK_USER_ID

#: The scopes an API key may hold: the account's own data.
_ALLOWED = {
    "account",
    "activities:read",
    "activities:write",
    "activities:upload",
    "followers:read",
    "followers:write",
    "gears:read",
    "gears:write",
    "health:read",
    "health:write",
    "health-targets:read",
    "health-targets:write",
    "notifications:read",
    "notifications:write",
    "users:read",
}
#: The scopes an API key never holds.
_EXCLUDED = {
    "account:export",
    "account:integrations",
    "account:security",
    "api-keys:read",
    "api-keys:write",
    "identity-providers:read",
    "identity-providers:write",
    "server-settings:logs",
    "server-settings:logs-clear",
    "server-settings:read",
    "server-settings:write",
    "sessions:read",
    "sessions:write",
    "users:read-all",
    "users:write",
}

KEY_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")


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
        """An unknown scope is refused on the scope it names."""
        with pytest.raises(ValidationError) as exc_info:
            users_api_keys_schema.UserApiKeyCreate(
                step_up={"current_password": "pw"},
                name="Test Key",
                scopes=["activities:upload", "totally:invalid-scope"],
            )
        assert [error["loc"] for error in exc_info.value.errors()] == [("scopes", 1)]

    @pytest.mark.parametrize("scope", sorted(_ALLOWED))
    def test_create_accepts_each_allowed_scope(self, scope):
        """A key may hold any scope over the account's own data."""
        key = users_api_keys_schema.UserApiKeyCreate(
            step_up={"current_password": "pw"}, name="Data Key", scopes=[scope]
        )

        assert key.scopes == [scope]

    def test_create_accepts_every_allowed_scope_at_once(self):
        """A key may hold every allowed scope together."""
        key = users_api_keys_schema.UserApiKeyCreate(
            step_up={"current_password": "pw"}, name="Full Key", scopes=sorted(_ALLOWED)
        )

        assert set(key.scopes) == _ALLOWED

    @pytest.mark.parametrize("scope", sorted(_EXCLUDED))
    def test_create_refuses_each_excluded_scope(self, scope):
        """A key never holds the account's security, export or provider links, nor any administrator scope."""
        with pytest.raises(ValidationError) as exc_info:
            users_api_keys_schema.UserApiKeyCreate(
                step_up={"current_password": "pw"}, name="Escalating Key", scopes=["gears:read", scope]
            )
        assert [error["loc"] for error in exc_info.value.errors()] == [("scopes", 1)]

    def test_every_scope_is_decided_as_allowed_or_excluded(self):
        """A new scope must be placed deliberately: on keys, or kept off them."""
        assert _ALLOWED.isdisjoint(_EXCLUDED)
        assert set(auth_constants.SCOPE_DICT) == _ALLOWED | _EXCLUDED

    @pytest.mark.parametrize("scope", ["profile", "profile:export", "profile:security", "health_targets:read"])
    def test_create_with_a_former_scope_name_fails(self, scope):
        """The names scopes had before their renames are refused like any unknown scope."""
        with pytest.raises(ValidationError):
            users_api_keys_schema.UserApiKeyCreate(
                step_up={"current_password": "pw"},
                name="Old Key",
                scopes=[scope],
            )

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
            id=KEY_ID,
            user_id=MOCK_USER_ID,
            name="My Key",
            key_prefix="abcdefgh",
            scopes='["activities:upload"]',
            expires_at=now + timedelta(days=30),
            last_used_at=None,
            created_at=now,
            is_active=True,
        )
        assert data.id == KEY_ID
        assert data.user_id == MOCK_USER_ID
        assert data.is_active is True
        assert data.scopes == ["activities:upload"]

    def test_read_schema_scopes_survive_a_created_read_round_trip(self):
        """The scopes stay a list when a read dump builds the creation response."""
        read = users_api_keys_schema.UserApiKeyRead(
            id=KEY_ID,
            user_id=MOCK_USER_ID,
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

    def test_read_schema_user_id_not_a_uuid_fails(self):
        """Test that user_id that is not a UUID fails validation."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            users_api_keys_schema.UserApiKeyRead(
                id=KEY_ID,
                user_id=0,
                name="My Key",
                key_prefix="abcdefgh",
                scopes='["activities:upload"]',
                expires_at=now + timedelta(days=30),
                last_used_at=None,
                created_at=now,
                is_active=True,
            )

    def test_read_schema_id_not_a_uuid_fails(self):
        """Test that an id that is not a UUID fails validation."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            users_api_keys_schema.UserApiKeyRead(
                id="some-uuid",
                user_id=MOCK_USER_ID,
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
            id=KEY_ID,
            user_id=MOCK_USER_ID,
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

    def test_created_schema_id_not_a_uuid_fails(self):
        """Test that an id that is not a UUID fails validation."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            users_api_keys_schema.UserApiKeyCreatedRead(
                id="some-uuid",
                user_id=MOCK_USER_ID,
                name="My Key",
                key_prefix="abcdefgh",
                scopes='["activities:upload"]',
                expires_at=now + timedelta(days=30),
                last_used_at=None,
                created_at=now,
                is_active=True,
                key="endurain_secrettoken",
            )

    def test_created_schema_extra_forbid(self):
        """Test that extra fields are forbidden on UserApiKeyCreatedRead."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            users_api_keys_schema.UserApiKeyCreatedRead(
                id=KEY_ID,
                user_id=MOCK_USER_ID,
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
