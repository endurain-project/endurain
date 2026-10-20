"""Gear nickname uniqueness against real PostgreSQL.

The service checks nothing before inserting; the unique index on
``(user_id, lower(nickname))`` is what holds when two requests, or a request and a
provider sync on another replica, create the same nickname at once.
"""

import importlib.util
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import func, select, text

import core.exceptions as core_exceptions
import modules.gears.gear.models as gear_models
import modules.gears.gear.service as gear_service
from tests._helpers.db import ensure_user
from tests._helpers.gears import gear_create

_THREADS = 6

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/1_gear_nickname_unique_per_user.py"
)


@pytest.fixture
def factory(pg_factory):
    for user_id in (1, 2):
        ensure_user(pg_factory, user_id)
    return pg_factory


def test_concurrent_creates_of_one_nickname_leave_one_gear(factory):
    barrier = threading.Barrier(_THREADS)
    outcomes: list = []

    def run(index: int) -> None:
        barrier.wait()
        with factory() as db:
            try:
                outcomes.append(gear_service.create_gear(gear_create("Road Bike" if index % 2 else "road bike"), 1, db))
            except Exception as err:
                db.rollback()
                outcomes.append(err)

    threads = [threading.Thread(target=run, args=(index,)) for index in range(_THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    conflicts = [o for o in outcomes if isinstance(o, core_exceptions.ConflictError)]
    assert len(outcomes) == _THREADS
    assert len(conflicts) == _THREADS - 1
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(gear_models.Gear)) == 1


def test_the_migration_renames_duplicates_before_enforcing_the_index(factory):
    with factory() as db:
        db.execute(text("DROP INDEX uq_gear_user_nickname"))
        for user_id, nickname in ((1, "Bike"), (1, " bike "), (1, "BIKE"), (2, "bike"), (1, "Shoes")):
            db.execute(
                text(
                    "INSERT INTO gear (nickname, gear_type, user_id, active, initial_kms, created_at) "
                    "VALUES (:n, 1, :u, true, 0, now())"
                ),
                {"n": nickname, "u": user_id},
            )
        db.commit()

        spec = importlib.util.spec_from_file_location("gear_nickname_unique", _MIGRATION_PATH)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with (
            patch.object(migration.op, "execute", side_effect=lambda sql: db.execute(text(sql))),
            patch.object(migration.op, "get_bind", return_value=db.connection()),
        ):
            migration.upgrade()
        db.commit()

        rows = db.execute(text("SELECT id, user_id, nickname FROM gear ORDER BY id")).all()

    first_id = rows[0].id
    assert [(row.user_id, row.nickname) for row in rows] == [
        (1, "Bike"),
        (1, f"bike ({first_id + 1})"),
        (1, f"BIKE ({first_id + 2})"),
        (2, "bike"),
        (1, "Shoes"),
    ]
