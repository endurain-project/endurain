"""One health record per user and day.

The services look for the day's record before creating one, which is read-then-write: two requests, or a request and
a Garmin Connect sync on another replica, can both see "not found". The unique ``(user_id, date)`` constraint is what
holds, and the loser is told, or the service updates the row the other writer created.
"""

import threading
from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa
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
from tests._factories.users import make_user

_THREADS = 6
_DAY = date(2026, 10, 1)


@pytest.fixture
def user(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
    return created


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


def _count(factory, model) -> int:
    with factory() as db:
        return db.scalar(sa.select(sa.func.count()).select_from(model))


def test_concurrent_steps_creates_for_one_day_leave_one_record_and_conflict_the_rest(committed_sessions, user):
    outcomes = _run_concurrently(
        committed_sessions,
        lambda index, db: steps_service.create_health_steps(
            user.id, steps_schema.HealthStepsCreate(date=_DAY, steps=1000 + index), db
        ),
    )

    errors = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
    assert len(outcomes) == _THREADS
    assert len(outcomes) - len(errors) == 1
    assert all(isinstance(error, core_exceptions.ConflictError) for error in errors)
    assert _count(committed_sessions, steps_models.HealthSteps) == 1


def test_concurrent_steps_upserts_for_one_day_leave_one_record(committed_sessions, user):
    def upsert(index, db):
        stored = steps_service.stage_upsert_health_steps(
            user.id, steps_schema.HealthStepsImport(date=_DAY, steps=1000 + index), db
        )
        db.commit()
        return stored

    outcomes = _run_concurrently(committed_sessions, upsert)

    assert len(outcomes) == _THREADS
    assert not [outcome for outcome in outcomes if isinstance(outcome, Exception)]
    assert _count(committed_sessions, steps_models.HealthSteps) == 1


def test_concurrent_water_creates_for_one_day_leave_one_record_and_conflict_the_rest(committed_sessions, user):
    outcomes = _run_concurrently(
        committed_sessions,
        lambda _index, db: water_service.create_health_water(
            user.id, water_schema.HealthWaterCreate(date=_DAY, amount_ml=Decimal(100)), db
        ),
    )

    errors = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
    assert len(outcomes) - len(errors) == 1
    assert all(isinstance(error, core_exceptions.ConflictError) for error in errors)
    with committed_sessions() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(water_models.HealthWater)) == 1
        assert db.scalar(sa.select(water_models.HealthWater.amount_ml)) == Decimal(100)


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (steps_models.HealthSteps, {"steps": 1}),
        (weight_models.HealthWeight, {"weight_kg": Decimal(70)}),
        (sleep_models.HealthSleep, {}),
        (water_models.HealthWater, {"amount_ml": Decimal(100)}),
    ],
    ids=["steps", "weight", "sleep", "water"],
)
def test_the_database_refuses_a_second_record_for_a_day_and_allows_one_per_user(db, model, values):
    first, second = make_user(db), make_user(db)
    db.add(model(user_id=first.id, date=_DAY, **values))
    db.add(model(user_id=second.id, date=_DAY, **values))
    db.flush()
    db.add(model(user_id=first.id, date=_DAY, **values))

    with pytest.raises(IntegrityError):
        db.flush()
