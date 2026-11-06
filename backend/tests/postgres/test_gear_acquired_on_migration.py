"""The gear ``created_at`` timestamp becomes the ``acquired_on`` date, against real PostgreSQL."""

import importlib.util
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import text

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
    ensure_user(pg_factory, 1)
    with pg_factory() as db:
        _legacy_gear_table(db)
        for nickname, moment in (("late", "2024-03-05 23:30:00-02"), ("early", "2024-03-05 00:30:00+05")):
            db.execute(
                text(
                    "INSERT INTO gear (nickname, gear_type, user_id, active, initial_distance, created_at, version) "
                    "VALUES (:n, 1, 1, true, 0, :m, 1)"
                ),
                {"n": nickname, "m": moment},
            )
        db.commit()
        migration = _migration()

        _run(db, migration, "upgrade")
        upgraded = dict(db.execute(text("SELECT nickname, acquired_on FROM gear")).all())
        db.execute(
            text(
                "INSERT INTO gear (nickname, gear_type, user_id, active, initial_distance, version) VALUES ('d', 1, 1, true, 0, 1)"
            )
        )
        defaulted = db.scalar(text("SELECT acquired_on FROM gear WHERE nickname = 'd'"))
        db.execute(text("DELETE FROM gear WHERE nickname = 'd'"))
        _run(db, migration, "downgrade")
        restored = dict(db.execute(text("SELECT nickname, created_at::date FROM gear")).all())

    assert upgraded == {"late": date(2024, 3, 6), "early": date(2024, 3, 4)}
    assert defaulted == date.today()
    assert restored == {"late": date(2024, 3, 6), "early": date(2024, 3, 4)}
