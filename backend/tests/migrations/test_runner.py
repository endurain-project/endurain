"""How pending data migrations are run at startup: in order, off the event loop thread, stopping at a failure."""

import asyncio
import threading

import pytest

import migrations.utils as migrations_utils
from tests._factories.migrations import make_migration


@pytest.fixture
def handlers(monkeypatch):
    """Register data migration handlers for the test; the production registry holds none once they are retired."""

    def register(**by_id: object) -> None:
        for migration_id, handler in by_id.items():
            monkeypatch.setitem(migrations_utils._SYNC_MIGRATIONS, int(migration_id.removeprefix("m")), handler)

    return register


async def test_a_sync_migration_may_start_its_own_event_loop(db, handlers):
    """Startup awaits the runner on a running loop, where ``asyncio.run`` is refused."""
    ran: list[bool] = []

    async def nothing() -> None:
        pass

    def migration(_db):
        asyncio.run(nothing())
        ran.append(True)

    make_migration(db, 1)
    handlers(m1=migration)

    await migrations_utils.check_migrations_not_executed(db)

    assert ran == [True]


async def test_a_sync_migration_does_not_run_on_the_event_loop_thread(db, handlers):
    seen: list[int] = []
    make_migration(db, 1)
    handlers(m1=lambda _db: seen.append(threading.get_ident()))

    await migrations_utils.check_migrations_not_executed(db)

    assert seen and seen[0] != threading.get_ident()


async def test_migrations_run_in_order_and_a_failure_stops_the_rest(db, handlers):
    order: list[int] = []

    def fail(_db):
        order.append(2)
        raise RuntimeError("boom")

    for migration_id in (1, 2, 3):
        make_migration(db, migration_id)
    handlers(m1=lambda _db: order.append(1), m2=fail, m3=lambda _db: order.append(3))

    with pytest.raises(RuntimeError):
        await migrations_utils.check_migrations_not_executed(db)

    assert order == [1, 2]


async def test_an_executed_migration_and_one_without_a_handler_are_not_run(db, handlers):
    ran: list[int] = []
    make_migration(db, 1, executed=True)
    make_migration(db, 2)
    make_migration(db, 3)
    handlers(m1=lambda _db: ran.append(1), m3=lambda _db: ran.append(3))

    await migrations_utils.check_migrations_not_executed(db)

    assert ran == [3]


async def test_nothing_runs_when_no_migration_is_pending(db, handlers):
    ran: list[int] = []
    handlers(m1=lambda _db: ran.append(1))

    await migrations_utils.check_migrations_not_executed(db)

    assert ran == []
