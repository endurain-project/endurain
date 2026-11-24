"""Concurrent security-generation writers on a user without a row, against real PostgreSQL.

``bump`` is ``INSERT ... ON CONFLICT DO UPDATE`` and ``lock`` is ``INSERT ... ON CONFLICT DO NOTHING`` followed by a
row lock. Both are first-touch races between replicas: no row exists to lock, so only the conflict clause keeps two
writers from failing on the unique key or losing an increment.
"""

import threading
from collections.abc import Callable

from sqlalchemy import text

import modules.auth.security_generation.integration_service as security_generation_integration
from tests._factories.users import make_user

_WRITERS = 8


def _new_user(factory):
    with factory() as db:
        user = make_user(db)
        db.commit()
    return user


def _stored(factory, user_id):
    with factory() as db:
        return (
            db.execute(text("SELECT generation FROM account_security_generations WHERE user_id = :u"), {"u": user_id})
            .scalars()
            .all()
        )


def _race(factory, work: Callable[[object], object]) -> tuple[list[object], list[Exception]]:
    """Run ``work(session)`` in as many threads at once, each in its own committed session."""
    barrier = threading.Barrier(_WRITERS)
    results: list[object] = []
    errors: list[Exception] = []

    def run() -> None:
        try:
            with factory() as db:
                barrier.wait()
                results.append(work(db))
                db.commit()
        except Exception as err:
            errors.append(err)

    threads = [threading.Thread(target=run) for _ in range(_WRITERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results, errors


def test_simultaneous_first_bumps_each_count_and_make_one_row(committed_sessions):
    user = _new_user(committed_sessions)

    _, errors = _race(committed_sessions, lambda db: security_generation_integration.stage_bump(user.id, db))

    assert errors == []
    assert _stored(committed_sessions, user.id) == [_WRITERS]


def test_simultaneous_first_locks_each_read_zero_and_make_one_row(committed_sessions):
    user = _new_user(committed_sessions)

    _, errors = _race(committed_sessions, lambda db: security_generation_integration.matches_locked(user.id, 0, db))

    assert errors == []
    assert _stored(committed_sessions, user.id) == [0]


def test_a_lock_racing_a_bump_on_a_new_row_loses_no_increment(committed_sessions):
    user = _new_user(committed_sessions)
    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def bump() -> None:
        try:
            with committed_sessions() as db:
                barrier.wait()
                security_generation_integration.stage_bump(user.id, db)
                db.commit()
        except Exception as err:
            errors.append(err)

    def lock() -> None:
        try:
            with committed_sessions() as db:
                barrier.wait()
                security_generation_integration.matches_locked(user.id, 0, db)
                db.commit()
        except Exception as err:
            errors.append(err)

    threads = [threading.Thread(target=bump), threading.Thread(target=lock)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert _stored(committed_sessions, user.id) == [1]
