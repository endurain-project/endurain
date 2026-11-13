"""The gear ``created_at`` timestamp becomes the ``acquired_on`` date, against real PostgreSQL."""

import importlib.util
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import text

from tests._helpers.auth import MOCK_USER_ID
from tests._helpers.db import ensure_user

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/43_gear_acquired_on.py"


def _migration():
    spec = importlib.util.spec_from_file_location("gear_acquired_on", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, migration, direction):
    with patch.object(migration.op, "execute", side_effect=lambda sql: db.execute(text(sql))):
        getattr(migration, direction)()
    db.commit()


def _legacy_gear_table(db):
    """Put the gear table back to its shape before the migration."""
    db.execute(text("ALTER TABLE gear RENAME COLUMN acquired_on TO created_at"))
    db.execute(text("ALTER TABLE gear ALTER COLUMN created_at TYPE timestamptz USING created_at::timestamptz"))
    db.execute(text("ALTER TABLE gear ALTER COLUMN created_at DROP DEFAULT"))
    db.commit()


def test_upgrade_keeps_each_rows_utc_calendar_day_and_downgrade_restores_a_timestamp(pg_factory):
    ensure_user(pg_factory, MOCK_USER_ID)
    with pg_factory() as db:
        _legacy_gear_table(db)
        for nickname, moment in (("late", "2024-03-05 23:30:00-02"), ("early", "2024-03-05 00:30:00+05")):
            db.execute(
                text(
                    "INSERT INTO gear (id, nickname, gear_type, user_id, active, initial_distance, created_at, version) "
                    "VALUES (:id, :n, 1, :u, true, 0, :m, 1)"
                ),
                {"id": uuid.uuid4(), "n": nickname, "m": moment, "u": MOCK_USER_ID},
            )
        db.commit()
        migration = _migration()

        _run(db, migration, "upgrade")
        upgraded = dict(db.execute(text("SELECT nickname, acquired_on FROM gear")).all())
        db.execute(
            text(
                "INSERT INTO gear (id, nickname, gear_type, user_id, active, initial_distance, version) "
                "VALUES (:id, 'd', 1, :u, true, 0, 1)"
            ),
            {"id": uuid.uuid4(), "u": MOCK_USER_ID},
        )
        defaulted = db.scalar(text("SELECT acquired_on FROM gear WHERE nickname = 'd'"))
        db.execute(text("DELETE FROM gear WHERE nickname = 'd'"))
        _run(db, migration, "downgrade")
        restored = dict(db.execute(text("SELECT nickname, created_at::date FROM gear")).all())

    assert upgraded == {"late": date(2024, 3, 6), "early": date(2024, 3, 4)}
    assert defaulted == date.today()
    assert restored == {"late": date(2024, 3, 6), "early": date(2024, 3, 4)}
