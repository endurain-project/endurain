"""Gear nickname uniqueness against real PostgreSQL.

The service checks nothing before inserting; the unique index on
``(user_id, lower(nickname))`` is what holds when two requests, or a request and a
provider sync on another replica, create the same nickname at once.
"""

import threading

import pytest
from sqlalchemy import func, select

import core.exceptions as core_exceptions
import modules.gears.gear.models as gear_models
import modules.gears.gear.service as gear_service
from tests._factories.gears import gear_payload
from tests._factories.users import make_user

_THREADS = 6


@pytest.fixture
def factory(committed_sessions):
    return committed_sessions


@pytest.fixture
def owner(factory):
    with factory() as db:
        created = make_user(db)
        db.commit()
    return created


def test_concurrent_creates_of_one_nickname_leave_one_gear(factory, owner):
    barrier = threading.Barrier(_THREADS)
    outcomes: list = []

    def run(index: int) -> None:
        barrier.wait()
        with factory() as db:
            try:
                outcomes.append(
                    gear_service.create_gear(gear_payload("Road Bike" if index % 2 else "road bike"), owner.id, db)
                )
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
