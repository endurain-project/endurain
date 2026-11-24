"""The startup migration lock lets replicas starting together migrate one at a time, on real PostgreSQL."""

import threading
import time

import pytest
from sqlalchemy import Connection, text

import core.database as core_database
import migrations.startup as migrations_startup

#: How long a test waits for another thread to reach a state; a bound, never a pause.
_WITHIN_SECONDS = 10


def _autocommit() -> Connection:
    return core_database.engine.connect().execution_options(isolation_level="AUTOCOMMIT")


def _hold_the_lock(connection: Connection) -> None:
    connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": migrations_startup._MIGRATION_LOCK_KEY})


def _release_the_lock(connection: Connection) -> None:
    connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": migrations_startup._MIGRATION_LOCK_KEY})


def _until(condition) -> None:
    deadline = time.monotonic() + _WITHIN_SECONDS
    while not condition():
        assert time.monotonic() < deadline, "the condition did not hold in time"


def _another_backend_asked_for_the_lock(holder: Connection) -> bool:
    """Whether a session other than the holder has run a statement on the migration lock."""
    return bool(
        holder.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                "AND pid <> pg_backend_pid() AND query LIKE '%advisory_lock%'"
            )
        ).scalar_one()
    )


class TestMigrationLock:
    def test_a_replica_waiting_for_the_lock_does_not_block_the_migrators_concurrent_index_build(
        self, committed_sessions
    ):
        """``CREATE INDEX CONCURRENTLY`` waits for every older snapshot; a waiter must hold none.

        A waiter blocked inside ``pg_advisory_lock`` holds one, and the build then deadlocks with it.
        """
        entered = threading.Event()

        def replica() -> None:
            with migrations_startup.migration_lock():
                entered.set()

        with _autocommit() as migrator:
            migrator.execute(text("CREATE TABLE lock_probe (id int)"))
            _hold_the_lock(migrator)
            waiter = threading.Thread(target=replica)
            waiter.start()
            try:
                _until(lambda: _another_backend_asked_for_the_lock(migrator))

                migrator.execute(text("SET lock_timeout = '5s'"))
                migrator.execute(text("CREATE INDEX CONCURRENTLY lock_probe_id ON lock_probe (id)"))

                assert not entered.is_set()
            finally:
                _release_the_lock(migrator)
                waiter.join(_WITHIN_SECONDS)

        assert entered.is_set()

    def test_the_lock_is_free_again_after_the_block(self, committed_sessions):
        with migrations_startup.migration_lock():
            pass

        with _autocommit() as other:
            taken = other.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": migrations_startup._MIGRATION_LOCK_KEY}
            ).scalar_one()
            _release_the_lock(other)

        assert taken is True

    def test_a_replica_gives_up_when_the_lock_is_not_free_in_time(self, committed_sessions, monkeypatch):
        monkeypatch.setattr(migrations_startup, "_MIGRATION_LOCK_TIMEOUT_SECONDS", 0.2)

        with _autocommit() as migrator:
            _hold_the_lock(migrator)
            try:
                with pytest.raises(TimeoutError, match="migration lock"), migrations_startup.migration_lock():
                    pytest.fail("the block ran without the lock")
            finally:
                _release_the_lock(migrator)
