"""Bring the schema and the data to the current version when the backend starts.

The application's own startup step: it runs the Alembic and substrate upgrades and the data migrations in this
package, so it lives beside them rather than in ``core``, which knows nothing of the application.
"""

import time
from collections.abc import Generator
from contextlib import contextmanager

import jasil.migrations as jasil_migrations
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, text

import core.logger as core_logger
import migrations.utils as migrations_utils
from alembic import command
from core.database import SessionLocal, engine

logger = core_logger.get_logger(__name__)

# Arbitrary constant identifying the migration lock among the database's advisory locks.
_MIGRATION_LOCK_KEY = 7_203_419_001
_MIGRATION_LOCK_TIMEOUT_SECONDS = 600
#: Pause between two attempts to take the migration lock while another replica holds it.
_MIGRATION_LOCK_POLL_SECONDS = 0.5


@contextmanager
def migration_lock() -> Generator[None]:
    """Hold the database-wide migration lock, so replicas starting together migrate one at a time.

    The others wait, then find the schema and data already current. The session-level advisory lock sits on an
    AUTOCOMMIT connection, which stays out of a transaction so an idle-in-transaction timeout cannot end the
    session (and release the lock) during a slow migration.

    A replica waits by trying the lock again (``pg_try_advisory_lock``), not by blocking in ``pg_advisory_lock``:
    a statement blocked there holds a snapshot for as long as it waits, and ``CREATE INDEX CONCURRENTLY`` in the
    migrating replica waits for every older snapshot, so the two would deadlock and the migration would fail.

    Raises:
        TimeoutError: When the lock is not free within ``_MIGRATION_LOCK_TIMEOUT_SECONDS``.
    """
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as lock_connection:
        deadline = time.monotonic() + _MIGRATION_LOCK_TIMEOUT_SECONDS
        while not lock_connection.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": _MIGRATION_LOCK_KEY}
        ).scalar_one():
            # A replica waits for the one migrating, but not forever if that one hangs.
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"The migration lock was not free within {_MIGRATION_LOCK_TIMEOUT_SECONDS} seconds; "
                    "another replica is still migrating the database"
                )
            time.sleep(_MIGRATION_LOCK_POLL_SECONDS)
        try:
            yield
        finally:
            lock_connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _MIGRATION_LOCK_KEY})


def require_known_revision(connection: Connection, script: ScriptDirectory) -> None:
    """Refuse a database at a revision the script directory does not know, before any revision runs.

    The history starts at the v0.21 baseline, so a v0.20 or older database sits at a revision that is gone from it. A
    fresh database (no version table) and one at any revision of the script directory pass. The check only reads.

    Args:
        connection: A connection to the database to check.
        script: The application's revision graph.

    Raises:
        RuntimeError: When a current revision is not in the script directory.
    """
    known = {revision.revision for revision in script.walk_revisions()}
    if not set(MigrationContext.configure(connection).get_current_heads()) <= known:
        raise RuntimeError(
            "This database is at a revision this release does not know. Endurain v0.22 upgrades only from v0.21.x: "
            "if this database is older, start the latest v0.21.x release, let it finish its upgrade and data "
            "migrations, then upgrade again. If it was used by a newer release, run that release or restore a "
            "backup taken before it."
        )


def run_alembic_upgrade() -> None:
    """Run Alembic upgrade to head.

    Critical: failure here aborts startup because the application cannot guarantee schema correctness.
    The caller holds :func:`migration_lock`.

    Raises:
        RuntimeError: When the database is at a revision this release does not know; nothing has been written to it.
    """
    alembic_cfg = Config("alembic.ini")
    with engine.connect() as connection:
        require_known_revision(connection, ScriptDirectory.from_config(alembic_cfg))
    # Disable Alembic's own logger configuration to avoid conflicts with FastAPI / our main logger.
    alembic_cfg.attributes["configure_logger"] = False
    command.upgrade(alembic_cfg, "head")


def bootstrap_substrate_schema(engine: Engine) -> None:
    """Adopt, upgrade, and verify the substrate's migration history.

    A fresh database is left for JASIL's upgrade to create the substrate tables, and a database that already holds
    JASIL's version table (every v0.21.x install after its first start) continues through the normal upgrade path.
    Only a v0.21 database whose startup stopped between the Alembic upgrade and this step still holds the unprefixed
    legacy ``event_log``, ``event_outbox`` and ``processing_jobs``: JASIL validates that complete, unversioned schema
    against its installed migration head before adopting it.

    Must run after the application's own Alembic upgrade.

    Args:
        engine: The engine of the database to bootstrap.
    """
    if jasil_migrations.adopt_existing_schema(engine):
        logger.info("Adopted existing substrate tables", extra=core_logger.context(console=True))
    jasil_migrations.upgrade(engine)
    jasil_migrations.verify_schema_current(engine)


async def check_migrations() -> None:
    """Check for pending custom migration records.

    Args:
        None.

    Returns:
        None.

    Raises:
        Exception: Propagates migration check failures.
    """
    logger.info("Checking for migrations not executed", extra=core_logger.context(console=True))

    with SessionLocal() as db:
        await migrations_utils.check_migrations_not_executed(db)

    logger.info("Migration check completed", extra=core_logger.context(console=True))


async def migrate_schema_and_data() -> None:
    """Bring the schema and the data to the current version, under the migration lock.

    Runs the Alembic upgrade, the substrate's upgrade and the pending data migrations as one locked unit, so a
    second replica never runs a data migration beside the first.

    Raises:
        Exception: Propagates any migration failure, which aborts startup.
    """
    with migration_lock():
        run_alembic_upgrade()
        bootstrap_substrate_schema(engine)
        await check_migrations()
