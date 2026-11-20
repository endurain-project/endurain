"""Every startup migration step runs while one lock is held, so replicas migrate one at a time."""

import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa
from tests._helpers import alembic_chain

import migrations.startup as migrations_startup


def test_every_step_runs_while_the_lock_is_held():
    order: list[object] = []

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
        patch.object(
            migrations_startup, "bootstrap_substrate_schema", lambda engine: order.append(("substrate", engine))
        ),
        patch.object(migrations_startup, "check_migrations", AsyncMock(side_effect=lambda: order.append("data"))),
    ):
        asyncio.run(migrations_startup.migrate_schema_and_data())

    assert order == ["lock", "alembic", ("substrate", migrations_startup.engine), "data", "unlock"]


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


def _check_source(revision: str | None) -> None:
    """Run the pre-flight check on an in-memory database at ``revision`` (no version table when ``None``)."""
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            if revision is not None:
                connection.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
                connection.execute(sa.text("INSERT INTO alembic_version VALUES (:revision)"), {"revision": revision})
            migrations_startup.require_known_revision(connection, alembic_chain.script_directory())
    finally:
        engine.dispose()


@pytest.mark.parametrize("revision", [None, alembic_chain.V0_21_HEAD, "b6cf67a93d94", "50ac9225ce4f"])
def test_the_pre_flight_lets_a_fresh_or_known_database_through(revision):
    _check_source(revision)


@pytest.mark.parametrize("revision", ["d54bdd779392", "c5cfe02a11c2", "353455bea2a5", "not-a-known-revision"])
def test_the_pre_flight_refuses_a_database_at_a_revision_the_script_does_not_know(revision):
    with pytest.raises(RuntimeError, match=r"revision this release does not know.*upgrades only from v0\.21\.x"):
        _check_source(revision)
