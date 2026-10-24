"""One health record per user and day against real PostgreSQL.

The services look for the day's record before creating one, which is read-then-write: two
requests, or a request and a Garmin Connect sync on another replica, can both see "not found".
The unique ``(user_id, date)`` constraint is what holds, and the service then updates the row
the other writer created.
"""

import importlib.util
import threading
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

import modules.health.health_sleep.models as sleep_models
import modules.health.health_steps.models as steps_models
import modules.health.health_steps.schema as steps_schema
import modules.health.health_steps.service as steps_service
import modules.health.health_water.models as water_models
import modules.health.health_water.schema as water_schema
import modules.health.health_water.service as water_service
import modules.health.health_weight.models as weight_models
from tests._helpers.db import ensure_user

_THREADS = 6
_DAY = date(2026, 10, 1)

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/11_health_one_record_per_day.py"
_TABLES = ("health_steps", "health_weight", "health_sleep", "health_water")


@pytest.fixture
def factory(pg_factory):
    for user_id in (1, 2):
        ensure_user(pg_factory, user_id)
    return pg_factory


def _run_concurrently(factory, work) -> list:
    barrier = threading.Barrier(_THREADS)
    outcomes: list = []

    def run(index: int) -> None:
        barrier.wait()
        with factory() as db:
            try:
                outcomes.append(work(index, db))
            except Exception as err:
                db.rollback()
                outcomes.append(err)

    threads = [threading.Thread(target=run, args=(index,)) for index in range(_THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    return outcomes


def test_concurrent_steps_for_one_day_leave_one_record(factory):
    outcomes = _run_concurrently(
        factory,
        lambda index, db: steps_service.create_health_steps(
            1, steps_schema.HealthStepsCreate(date=_DAY, steps=1000 + index), db
        ),
    )

    assert len(outcomes) == _THREADS
    assert not [outcome for outcome in outcomes if isinstance(outcome, Exception)]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(steps_models.HealthSteps)) == 1


def test_concurrent_water_intakes_for_one_day_are_all_counted(factory):
    outcomes = _run_concurrently(
        factory,
        lambda _index, db: water_service.create_health_water(
            1, water_schema.HealthWaterCreate(date=_DAY, amount_ml=Decimal(100)), db
        ),
    )

    assert not [outcome for outcome in outcomes if isinstance(outcome, Exception)]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(water_models.HealthWater)) == 1
        assert db.scalar(select(water_models.HealthWater.amount_ml)) == Decimal(100 * _THREADS)


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (steps_models.HealthSteps, {"steps": 1}),
        (weight_models.HealthWeight, {"weight": Decimal(70)}),
        (sleep_models.HealthSleep, {}),
        (water_models.HealthWater, {"amount_ml": Decimal(100)}),
    ],
)
def test_the_database_refuses_a_second_record_for_a_day(factory, model, values):
    with factory() as db:
        db.add(model(user_id=1, date=_DAY, **values))
        db.add(model(user_id=2, date=_DAY, **values))
        db.commit()
        db.add(model(user_id=1, date=_DAY, **values))
        with pytest.raises(IntegrityError):
            db.commit()


def _load_migration():
    spec = importlib.util.spec_from_file_location("health_one_record_per_day", _MIGRATION_PATH)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_the_migration_merges_duplicates_before_enforcing_the_constraints(factory):
    with factory() as db:
        for table in _TABLES:
            db.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT uq_{table}_user_date"))
        for steps in (100, 200, 300):
            db.execute(
                text("INSERT INTO health_steps (user_id, date, steps) VALUES (1, :d, :s)"), {"d": _DAY, "s": steps}
            )
        db.execute(text("INSERT INTO health_steps (user_id, date, steps) VALUES (2, :d, 50)"), {"d": _DAY})
        for ml in (100, 250):
            db.execute(
                text("INSERT INTO health_water (user_id, date, amount_ml) VALUES (1, :d, :ml)"), {"d": _DAY, "ml": ml}
            )
        db.commit()

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

        steps = db.execute(text("SELECT user_id, steps FROM health_steps ORDER BY user_id")).all()
        water = db.execute(text("SELECT user_id, amount_ml FROM health_water")).all()

    assert [tuple(row) for row in steps] == [(1, 300), (2, 50)]
    assert [(row.user_id, row.amount_ml) for row in water] == [(1, Decimal(350))]
