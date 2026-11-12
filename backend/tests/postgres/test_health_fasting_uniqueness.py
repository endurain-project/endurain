"""One in-progress fast per user against real PostgreSQL.

The service looks for a running fast before starting one, which is read-then-write: two requests,
on this replica or another, can both see "none". The partial unique index on in-progress rows is what
holds, and the loser is answered as a conflict.
"""

import threading
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text

import core.etag as core_etag
import core.exceptions as core_exceptions
import modules.health.health_fasting.models as fasting_models
import modules.health.health_fasting.schema as fasting_schema
import modules.health.health_fasting.service as fasting_service
from tests._helpers import alembic_chain
from tests._helpers.db import ensure_user

_THREADS = 6
_START = datetime(2026, 10, 1, 8, 0, 0, tzinfo=UTC)
_INDEX = "uq_health_fasting_one_in_progress_per_user"

_REVISION_BEFORE = "c3e9a5d72b18"
_REVISION = "d8b4f1a7c3e5"


@pytest.fixture
def factory(pg_factory):
    for user_id in (1, 2):
        ensure_user(pg_factory, user_id)
    return pg_factory


def test_concurrent_starts_leave_one_running_fast(factory):
    barrier = threading.Barrier(_THREADS)
    outcomes: list = []

    def run() -> None:
        barrier.wait()
        with factory() as db:
            try:
                outcomes.append(
                    fasting_service.create_health_fasting(
                        1, fasting_schema.HealthFastingCreate(fast_start_time=_START), db
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
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(fasting_models.HealthFasting)) == 1


def test_a_finished_fast_does_not_block_a_new_one(factory):
    with factory() as db:
        first = fasting_service.create_health_fasting(1, fasting_schema.HealthFastingCreate(fast_start_time=_START), db)
        fasting_service.complete_health_fasting(
            1,
            first.id,
            fasting_schema.HealthFastingComplete(fast_end_time=datetime(2026, 10, 1, 20, 0, 0, tzinfo=UTC)),
            db,
            if_match=core_etag.format_etag(first.version),
        )
        fasting_service.create_health_fasting(
            1, fasting_schema.HealthFastingCreate(fast_start_time=datetime(2026, 10, 1, 20, 0, 0, tzinfo=UTC)), db
        )

        assert db.scalar(select(func.count()).select_from(fasting_models.HealthFasting)) == 2


def test_the_migration_cancels_older_running_fasts_before_enforcing_the_index(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION_BEFORE)
    with upgrade_db.begin() as connection:
        alembic_chain.seed_users(connection)
        for hour in (6, 8, 10):
            connection.execute(
                text("INSERT INTO health_fasting (user_id, fast_start_time, status) VALUES (1, :start, 'in_progress')"),
                {"start": datetime(2026, 10, 1, hour, 0, 0)},
            )
        connection.execute(
            text("INSERT INTO health_fasting (user_id, fast_start_time, status) VALUES (2, :start, 'in_progress')"),
            {"start": _START},
        )

    alembic_chain.upgrade(upgrade_db, _REVISION)

    with upgrade_db.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT user_id, extract(hour FROM fast_start_time)::int AS hour, status FROM health_fasting ORDER BY id"
            )
        ).all()
    assert [tuple(row) for row in rows] == [
        (1, 6, "cancelled"),
        (1, 8, "cancelled"),
        (1, 10, "in_progress"),
        (2, 8, "in_progress"),
    ]
