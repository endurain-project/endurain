"""One default-gear row per user against real PostgreSQL."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.users.users_default_gear.crud as default_gear_crud
from tests._helpers import alembic_chain
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID
from tests._helpers.db import ensure_user

_MIGRATION_FILE = "2_constraints_versions_and_settings.py"
_MIGRATION_STEP = "users_default_gear_one_per_user"
_REVISION_BEFORE = "c5cfe02a11c2"


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


def test_the_migration_keeps_the_newest_row_of_each_user_before_enforcing_the_constraint(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION_BEFORE)
    alembic_chain.run_steps_before(upgrade_db, _MIGRATION_FILE, _MIGRATION_STEP)
    with upgrade_db.begin() as connection:
        alembic_chain.seed_users(connection)
        for user_id in (1, 1, 2):
            connection.execute(text("INSERT INTO users_default_gear (user_id) VALUES (:u)"), {"u": user_id})
        newest = connection.execute(text("SELECT max(id) FROM users_default_gear WHERE user_id = 1")).scalar_one()

    alembic_chain.run_step(upgrade_db, _MIGRATION_FILE, _MIGRATION_STEP)

    with upgrade_db.connect() as connection:
        rows = connection.execute(text("SELECT id, user_id FROM users_default_gear ORDER BY user_id")).all()
    assert len(rows) == 2
    assert rows[0].id == newest
    with pytest.raises(IntegrityError), upgrade_db.begin() as connection:
        connection.execute(text("INSERT INTO users_default_gear (user_id) VALUES (1)"))
