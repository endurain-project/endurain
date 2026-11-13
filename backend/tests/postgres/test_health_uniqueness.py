"""One health record per user and day against real PostgreSQL.

The services look for the day's record before creating one, which is read-then-write: two
requests, or a request and a Garmin Connect sync on another replica, can both see "not found".
The unique ``(user_id, date)`` constraint is what holds, and the service then updates the row
the other writer created.
"""

import threading
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.health.health_sleep.models as sleep_models
import modules.health.health_steps.models as steps_models
import modules.health.health_steps.schema as steps_schema
import modules.health.health_steps.service as steps_service
import modules.health.health_water.models as water_models
import modules.health.health_water.schema as water_schema
import modules.health.health_water.service as water_service
import modules.health.health_weight.models as weight_models
from tests._helpers import alembic_chain
from tests._helpers.db import ensure_user

_THREADS = 6
_DAY = date(2026, 10, 1)

_REVISION_BEFORE = "f4c8a2e6b7d1"
_REVISION = "a6d2f8c41e75"


_USER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
_OTHER_USER_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


@pytest.fixture
def factory(pg_factory):
    for user_id in (_USER_ID, _OTHER_USER_ID):
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


def test_concurrent_steps_creates_for_one_day_leave_one_record_and_conflict_the_rest(factory):
    outcomes = _run_concurrently(
        factory,
        lambda index, db: steps_service.create_health_steps(
            _USER_ID, steps_schema.HealthStepsCreate(date=_DAY, steps=1000 + index), db
        ),
    )

    errors = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
    assert len(outcomes) == _THREADS
    assert len(outcomes) - len(errors) == 1
    assert all(isinstance(error, core_exceptions.ConflictError) for error in errors)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(steps_models.HealthSteps)) == 1


def test_concurrent_steps_upserts_for_one_day_leave_one_record(factory):
    def upsert(index, db):
        stored = steps_service.stage_upsert_health_steps(
            _USER_ID, steps_schema.HealthStepsCreate(date=_DAY, steps=1000 + index), db
        )
        db.commit()
        return stored

    outcomes = _run_concurrently(factory, upsert)

    assert len(outcomes) == _THREADS
    assert not [outcome for outcome in outcomes if isinstance(outcome, Exception)]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(steps_models.HealthSteps)) == 1


def test_concurrent_water_creates_for_one_day_leave_one_record_and_conflict_the_rest(factory):
    outcomes = _run_concurrently(
        factory,
        lambda _index, db: water_service.create_health_water(
            _USER_ID, water_schema.HealthWaterCreate(date=_DAY, amount_ml=Decimal(100)), db
        ),
    )

    errors = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
    assert len(outcomes) - len(errors) == 1
    assert all(isinstance(error, core_exceptions.ConflictError) for error in errors)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(water_models.HealthWater)) == 1
        assert db.scalar(select(water_models.HealthWater.amount_ml)) == Decimal(100)


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (steps_models.HealthSteps, {"steps": 1}),
        (weight_models.HealthWeight, {"weight_kg": Decimal(70)}),
        (sleep_models.HealthSleep, {}),
        (water_models.HealthWater, {"amount_ml": Decimal(100)}),
    ],
)
def test_the_database_refuses_a_second_record_for_a_day(factory, model, values):
    with factory() as db:
        db.add(model(user_id=_USER_ID, date=_DAY, **values))
        db.add(model(user_id=_OTHER_USER_ID, date=_DAY, **values))
        db.commit()
        db.add(model(user_id=_USER_ID, date=_DAY, **values))
        with pytest.raises(IntegrityError):
            db.commit()


def test_the_migration_merges_duplicates_before_enforcing_the_constraints(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION_BEFORE)
    with upgrade_db.begin() as connection:
        alembic_chain.seed_users(connection)
        for steps in (100, 200, 300):
            connection.execute(
                text("INSERT INTO health_steps (user_id, date, steps) VALUES (1, :d, :s)"), {"d": _DAY, "s": steps}
            )
        connection.execute(text("INSERT INTO health_steps (user_id, date, steps) VALUES (2, :d, 50)"), {"d": _DAY})
        for ml in (100, 250):
            connection.execute(
                text("INSERT INTO health_water (user_id, date, amount_ml) VALUES (1, :d, :ml)"), {"d": _DAY, "ml": ml}
            )

    alembic_chain.upgrade(upgrade_db, _REVISION)

    with upgrade_db.connect() as connection:
        steps = connection.execute(text("SELECT user_id, steps FROM health_steps ORDER BY user_id")).all()
        water = connection.execute(text("SELECT user_id, amount_ml FROM health_water")).all()
    assert [tuple(row) for row in steps] == [(1, 300), (2, 50)]
    assert [(row.user_id, row.amount_ml) for row in water] == [(1, Decimal(350))]
