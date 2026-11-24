"""Startup brings the schema and the data current under one lock, so replicas migrate one at a time."""

from pathlib import Path

import pytest
import sqlalchemy as sa

import core.database as core_database
import migrations.startup as migrations_startup
import migrations.utils as migrations_utils
from tests._factories.migrations import make_migration
from tests._helpers import alembic_chain

_APP_DIR = Path(__file__).resolve().parents[2] / "app"


@pytest.fixture
def startup_in_app_dir(monkeypatch):
    """Run startup as the process does: from the application directory, where ``alembic.ini`` lives."""
    monkeypatch.chdir(_APP_DIR)


def _lock_is_free() -> bool:
    """Try the migration lock from another session and release it again."""
    with core_database.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as other:
        key = {"key": migrations_startup._MIGRATION_LOCK_KEY}
        taken = other.execute(sa.text("SELECT pg_try_advisory_lock(:key)"), key).scalar_one()
        if taken:
            other.execute(sa.text("SELECT pg_advisory_unlock(:key)"), key)
        return taken


async def test_a_pending_data_migration_runs_while_the_lock_is_held(
    committed_sessions, startup_in_app_dir, monkeypatch
):
    with committed_sessions() as db:
        make_migration(db, 41)
        db.commit()
    held: list[bool] = []
    monkeypatch.setitem(migrations_utils._SYNC_MIGRATIONS, 41, lambda _db: held.append(not _lock_is_free()))

    await migrations_startup.migrate_schema_and_data()

    assert held == [True]
    assert _lock_is_free()


async def test_the_lock_is_released_when_a_step_fails(committed_sessions, startup_in_app_dir, monkeypatch):
    with committed_sessions() as db:
        make_migration(db, 41)
        db.commit()

    def fail(_db) -> None:
        raise RuntimeError("boom")

    monkeypatch.setitem(migrations_utils._SYNC_MIGRATIONS, 41, fail)

    with pytest.raises(RuntimeError, match="boom"):
        await migrations_startup.migrate_schema_and_data()

    assert _lock_is_free()


async def test_startup_on_a_current_database_changes_nothing(committed_sessions, startup_in_app_dir):
    with core_database.engine.connect() as connection:
        before = connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()

    await migrations_startup.migrate_schema_and_data()

    with core_database.engine.connect() as connection:
        assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == before


def _check_source(engine, revision: str | None) -> None:
    """Run the pre-flight check on a database at ``revision`` (no version table when ``None``)."""
    with engine.begin() as connection:
        if revision is not None:
            connection.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            connection.execute(sa.text("INSERT INTO alembic_version VALUES (:revision)"), {"revision": revision})
        migrations_startup.require_known_revision(connection, alembic_chain.script_directory())


@pytest.mark.parametrize("revision", [None, alembic_chain.V0_21_HEAD, "b6cf67a93d94", "50ac9225ce4f"])
def test_the_pre_flight_lets_a_fresh_or_known_database_through(upgrade_db, revision):
    _check_source(upgrade_db, revision)


@pytest.mark.parametrize("revision", ["d54bdd779392", "c5cfe02a11c2", "353455bea2a5", "not-a-known-revision"])
def test_the_pre_flight_refuses_a_database_at_a_revision_the_script_does_not_know(upgrade_db, revision):
    with pytest.raises(RuntimeError, match=r"revision this release does not know.*upgrades only from v0\.21\.x"):
        _check_source(upgrade_db, revision)
