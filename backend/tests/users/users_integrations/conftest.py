"""Fixtures for the integrations tests."""

import pytest

from tests._factories.users import make_user


@pytest.fixture
def user(db):
    """A user with the empty integrations row every account starts with."""
    return make_user(db)


@pytest.fixture
def other(db):
    """Another user."""
    return make_user(db)
