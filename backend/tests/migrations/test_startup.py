"""Every startup migration step runs while one lock is held, so replicas migrate one at a time."""

import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

import migrations.startup as migrations_startup


def test_every_step_runs_while_the_lock_is_held():
    order: list[str] = []

    @contextmanager
    def lock():
        order.append("lock")
        try:
            yield
        finally:
            order.append("unlock")

    with (
        patch.object(migrations_startup, "migration_lock", lock),
        patch.object(migrations_startup, "run_alembic_upgrade", lambda: order.append("alembic")),
        patch.object(migrations_startup, "bootstrap_substrate_schema", lambda: order.append("substrate")),
        patch.object(migrations_startup, "check_migrations", AsyncMock(side_effect=lambda: order.append("data"))),
    ):
        asyncio.run(migrations_startup.migrate_schema_and_data())

    assert order == ["lock", "alembic", "substrate", "data", "unlock"]


def test_the_lock_is_released_when_a_step_fails():
    order: list[str] = []

    @contextmanager
    def lock():
        try:
            yield
        finally:
            order.append("unlock")

    def fail() -> None:
        raise RuntimeError("boom")

    with (
        patch.object(migrations_startup, "migration_lock", lock),
        patch.object(migrations_startup, "run_alembic_upgrade", fail),
        pytest.raises(RuntimeError),
    ):
        asyncio.run(migrations_startup.migrate_schema_and_data())

    assert order == ["unlock"]
