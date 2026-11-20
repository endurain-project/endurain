"""One default-gear row per user against real PostgreSQL."""

import pytest

import core.exceptions as core_exceptions
import modules.users.users_default_gear.crud as default_gear_crud
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID
from tests._helpers.db import ensure_user


@pytest.fixture
def factory(pg_factory):
    ensure_user(pg_factory, MOCK_USER_ID)
    ensure_user(pg_factory, OTHER_USER_ID)
    return pg_factory


def test_a_second_row_for_a_user_is_refused_as_a_conflict(factory):
    with factory() as db:
        default_gear_crud.create_user_default_gear(MOCK_USER_ID, db)
        db.commit()

        with pytest.raises(core_exceptions.ConflictError):
            default_gear_crud.create_user_default_gear(MOCK_USER_ID, db)
        db.rollback()
