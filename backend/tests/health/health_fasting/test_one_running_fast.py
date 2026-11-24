"""One in-progress fast per user, on the real database.

The service looks for a running fast before starting one, which is read-then-write: two requests, on this replica or
another, can both see "none". The partial unique index on in-progress rows is what holds, and the loser is answered as
a conflict.
"""

import threading
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

import core.etag as core_etag
import core.exceptions as core_exceptions
import modules.health.health_fasting.models as fasting_models
import modules.health.health_fasting.schema as fasting_schema
import modules.health.health_fasting.service as fasting_service
from tests._factories.users import make_user

_THREADS = 6
_START = datetime(2026, 10, 1, 8, 0, 0, tzinfo=UTC)


def _count(factory) -> int:
    with factory() as db:
        return db.scalar(sa.select(sa.func.count()).select_from(fasting_models.HealthFasting))


def test_concurrent_starts_leave_one_running_fast(committed_sessions):
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
    barrier = threading.Barrier(_THREADS)
    outcomes: list = []

    def run() -> None:
        barrier.wait()
        with committed_sessions() as db:
            try:
                outcomes.append(
                    fasting_service.create_health_fasting(
                        user.id, fasting_schema.HealthFastingCreate(fast_start_time=_START), db
                    )
                )
            except Exception as err:
                db.rollback()
                outcomes.append(err)

    threads = [threading.Thread(target=run) for _ in range(_THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    errors = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
    assert len(outcomes) == _THREADS
    assert len(outcomes) - len(errors) == 1
    assert all(isinstance(error, core_exceptions.ConflictError) for error in errors)
    assert _count(committed_sessions) == 1


def test_a_finished_fast_does_not_block_a_new_one(db):
    user = make_user(db)
    first = fasting_service.create_health_fasting(
        user.id, fasting_schema.HealthFastingCreate(fast_start_time=_START), db
    )
    fasting_service.complete_health_fasting(
        user.id,
        first.id,
        fasting_schema.HealthFastingComplete(fast_end_time=datetime(2026, 10, 1, 20, 0, 0, tzinfo=UTC)),
        db,
        if_match=core_etag.format_etag(first.version),
    )

    fasting_service.create_health_fasting(
        user.id, fasting_schema.HealthFastingCreate(fast_start_time=datetime(2026, 10, 1, 20, 0, 0, tzinfo=UTC)), db
    )

    assert db.scalar(sa.select(sa.func.count()).select_from(fasting_models.HealthFasting)) == 2


def test_another_users_running_fast_does_not_block_a_start(db):
    first, second = make_user(db), make_user(db)
    fasting_service.create_health_fasting(first.id, fasting_schema.HealthFastingCreate(fast_start_time=_START), db)

    started = fasting_service.create_health_fasting(
        second.id, fasting_schema.HealthFastingCreate(fast_start_time=_START), db
    )

    assert started.user_id == second.id


def test_a_second_running_fast_is_a_conflict(db):
    user = make_user(db)
    fasting_service.create_health_fasting(user.id, fasting_schema.HealthFastingCreate(fast_start_time=_START), db)

    with pytest.raises(core_exceptions.ConflictError):
        fasting_service.create_health_fasting(
            user.id, fasting_schema.HealthFastingCreate(fast_start_time=datetime(2026, 10, 3, 8, tzinfo=UTC)), db
        )
