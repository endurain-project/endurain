"""Validation of the birthdate on the user and profile schemas."""

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

import modules.users.users.schema as users_schema


def _user(birthdate):
    return users_schema.UserBase(name="Test User", username="testuser", email="test@example.com", birthdate=birthdate)


def _profile(birthdate):
    return users_schema.ProfileUpdate(birthdate=birthdate)


@pytest.mark.parametrize("build", [_user, _profile])
class TestBirthdate:
    def test_a_date_and_its_iso_string_are_accepted(self, build):
        assert build(date(1990, 5, 17)).birthdate == date(1990, 5, 17)
        assert build("1990-05-17").birthdate == date(1990, 5, 17)

    def test_none_is_kept(self, build):
        assert build(None).birthdate is None

    def test_today_is_accepted(self, build):
        today = datetime.now(UTC).date()

        assert build(today).birthdate == today

    def test_a_date_before_1900_is_rejected(self, build):
        with pytest.raises(ValidationError):
            build(date(1899, 12, 31))

    def test_a_date_beyond_tomorrow_is_rejected(self, build):
        with pytest.raises(ValidationError):
            build(datetime.now(UTC).date() + timedelta(days=2))

    def test_the_year_2030_is_rejected(self, build):
        with pytest.raises(ValidationError):
            build("2030-01-01")
