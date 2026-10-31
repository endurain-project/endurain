"""One default-gear row per user against real PostgreSQL."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.users.users_default_gear.crud as default_gear_crud
from tests._helpers.db import ensure_user

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/12_users_default_gear_one_per_user.py"
)


@pytest.fixture
def factory(pg_factory):
    for user_id in (1, 2):
        ensure_user(pg_factory, user_id)
    return pg_factory


def _load_migration():
    spec = importlib.util.spec_from_file_location("users_default_gear_one_per_user", _MIGRATION_PATH)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_a_second_row_for_a_user_is_refused_as_a_conflict(factory):
    with factory() as db:
        default_gear_crud.create_user_default_gear(1, db)
        db.commit()

        with pytest.raises(core_exceptions.ConflictError):
            default_gear_crud.create_user_default_gear(1, db)
        db.rollback()


def test_the_migration_keeps_the_newest_row_of_each_user_before_enforcing_the_constraint(factory):
    with factory() as db:
        db.execute(text("ALTER TABLE users_default_gear DROP CONSTRAINT uq_users_default_gear_user_id"))
        for user_id in (1, 1, 2):
            db.execute(text("INSERT INTO users_default_gear (user_id) VALUES (:u)"), {"u": user_id})
        db.commit()
        newest = db.execute(text("SELECT max(id) FROM users_default_gear WHERE user_id = 1")).scalar_one()

        migration = _load_migration()
        with (
            patch.object(migration.op, "execute", side_effect=lambda sql: db.execute(text(sql))),
            patch.object(
                migration.op,
                "create_unique_constraint",
                side_effect=lambda name, table, cols: db.execute(
                    text(f"ALTER TABLE {table} ADD CONSTRAINT {name} UNIQUE ({', '.join(cols)})")
                ),
            ),
        ):
            migration.upgrade()
        db.commit()

        rows = db.execute(text("SELECT id, user_id FROM users_default_gear ORDER BY user_id")).all()
        assert len(rows) == 2
        assert rows[0].id == newest
        with pytest.raises(IntegrityError):
            db.execute(text("INSERT INTO users_default_gear (user_id) VALUES (1)"))
        db.rollback()
