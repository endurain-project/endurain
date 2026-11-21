"""Fixtures shared by the gears tests."""

import pytest

import modules.gears.gear.schema as gears_schema
import modules.users.users.schema as users_schema
from tests._factories.gears import make_gear
from tests._factories.users import make_user


@pytest.fixture
def user(db) -> users_schema.UserRead:
    """A user staged on the test's session."""
    return make_user(db)


@pytest.fixture
def other(db) -> users_schema.UserRead:
    """A second user staged on the test's session."""
    return make_user(db)


@pytest.fixture
def gear(db, user) -> gears_schema.GearRead:
    """A bike of ``user``."""
    return make_gear(db, user.id, nickname="Main bike")


@pytest.fixture
def other_gear(db, user) -> gears_schema.GearRead:
    """A second bike of ``user``."""
    return make_gear(db, user.id, nickname="Spare bike")
