"""Validation of the user's IANA timezone field."""

import pytest
from pydantic import ValidationError


def _user(**overrides):
    import modules.users.users.schema as users_schema

    fields = {
        "name": "Test User",
        "username": "testuser",
        "email": "test@example.com",
    }
    fields.update(overrides)
    return users_schema.UsersBase(**fields)


class TestUserTimezone:
    def test_defaults_to_none(self):
        assert _user().timezone is None

    def test_accepts_a_known_iana_name(self):
        assert _user(timezone="America/Los_Angeles").timezone == "America/Los_Angeles"

    def test_accepts_a_fixed_offset_zone(self):
        assert _user(timezone="Etc/GMT-9").timezone == "Etc/GMT-9"

    def test_rejects_an_unknown_name(self):
        """The value is handed to ZoneInfo and Intl, so garbage must not persist."""
        with pytest.raises(ValidationError) as err:
            _user(timezone="Not/AZone")
        assert "Unknown IANA timezone" in str(err.value)

    def test_rejects_a_utc_offset_string(self):
        with pytest.raises(ValidationError):
            _user(timezone="+09:00")
