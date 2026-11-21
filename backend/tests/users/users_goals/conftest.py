"""Fixtures for the goals tests."""

import pytest

from tests._factories.users import make_user


@pytest.fixture
def user(db):
    """A user whose week starts on Monday and whose day is read in UTC."""
    return make_user(db, timezone="UTC", first_day_of_week="monday")


@pytest.fixture
def other(db):
    """Another user."""
    return make_user(db, timezone="UTC")
