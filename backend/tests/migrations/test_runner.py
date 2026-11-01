"""Tests for migrations.utils: how pending data migrations are run at startup."""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import migrations.utils as migrations_utils


def _pending(*ids: int) -> list[MagicMock]:
    return [MagicMock(id=migration_id, name=f"m{migration_id}") for migration_id in ids]


def _run(sync: dict, pending: list) -> None:
    with (
        patch.object(migrations_utils.migrations_crud, "get_migrations_not_executed", return_value=pending),
        patch.object(migrations_utils, "_SYNC_MIGRATIONS", sync),
        patch.object(migrations_utils, "_ASYNC_MIGRATIONS", {}),
    ):
        asyncio.run(migrations_utils.check_migrations_not_executed(MagicMock()))


def test_a_sync_migration_may_start_its_own_event_loop():
    """Startup awaits the runner on a running loop, where ``asyncio.run`` is refused."""
    ran: list[bool] = []

    def migration(_db):
        asyncio.run(asyncio.sleep(0))
        ran.append(True)

    _run({1: migration}, _pending(1))

    assert ran == [True]


def test_a_sync_migration_does_not_run_on_the_event_loop_thread():
    loop_thread = threading.get_ident()
    seen: list[int] = []

    _run({1: lambda _db: seen.append(threading.get_ident())}, _pending(1))

    assert seen and seen[0] != loop_thread


def test_migrations_run_in_order_and_a_failure_stops_the_rest():
    order: list[int] = []

    def fail(_db):
        order.append(2)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        _run({1: lambda _db: order.append(1), 2: fail, 3: lambda _db: order.append(3)}, _pending(1, 2, 3))

    assert order == [1, 2]


def test_an_async_migration_is_awaited_on_the_loop():
    handler = AsyncMock()
    with (
        patch.object(migrations_utils.migrations_crud, "get_migrations_not_executed", return_value=_pending(4)),
        patch.object(migrations_utils, "_SYNC_MIGRATIONS", {}),
        patch.object(migrations_utils, "_ASYNC_MIGRATIONS", {4: handler}),
    ):
        asyncio.run(migrations_utils.check_migrations_not_executed(MagicMock()))

    handler.assert_awaited_once()
