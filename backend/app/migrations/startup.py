"""Bring the schema and the data to the current version when the backend starts.

The application's own startup step: it runs the Alembic and substrate upgrades and the data migrations in this
package, so it lives beside them rather than in ``core``, which knows nothing of the application.
"""

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

# The v0.21 head: v0.22 retired the v0.21 data migrations and upgrades only from a database at or past this revision.
_V0_21_HEAD = "e95a7c1d4b36"


@contextmanager
def migration_lock() -> Generator[None]:
    """Hold the database-wide migration lock, so replicas starting together migrate one at a time.

    The others wait, then find the schema and data already current. The session-level advisory lock sits on an
    AUTOCOMMIT connection, which stays out of a transaction so an idle-in-transaction timeout cannot end the
    session (and release the lock) during a slow migration.

    Raises:
        DBAPIError: When the lock is not granted within ``_MIGRATION_LOCK_TIMEOUT_SECONDS``.
    """
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as lock_connection:
        locked = False
        try:
            # A replica waits for the one migrating, but not forever if that one hangs.
            lock_connection.execute(text(f"SET lock_timeout = '{_MIGRATION_LOCK_TIMEOUT_SECONDS}s'"))
            lock_connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _MIGRATION_LOCK_KEY})
            locked = True
            yield
        finally:
            # The connection goes back to the pool; do not leave the timeout on it, even when the wait timed out.
            try:
                if locked:
                    lock_connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _MIGRATION_LOCK_KEY})
            finally:
                lock_connection.execute(text("RESET lock_timeout"))


def require_v0_21_or_newer(connection: Connection, script: ScriptDirectory) -> None:
    """Refuse a database whose Alembic revision is older than the v0.21 head, before any revision runs.

    A fresh database (no version table), one at or past the v0.21 head, and one at a revision the script directory does
    not know all pass; Alembic reports the unknown revision itself. The check only reads.

    Args:
        connection: A connection to the database to check.
        script: The application's revision graph.

    Raises:
        RuntimeError: When a current revision is a strict ancestor of the v0.21 head.
    """
    older = {revision.revision for revision in script.walk_revisions(base="base", head=_V0_21_HEAD)} - {_V0_21_HEAD}
    if older.intersection(MigrationContext.configure(connection).get_current_heads()):
        raise RuntimeError(
            "Endurain v0.22 upgrades only from v0.21.x. This database is at an older release. Start the latest "
            "v0.21.x release, let it finish its upgrade and data migrations, then upgrade again."
        )


def run_alembic_upgrade() -> None:
    """Run Alembic upgrade to head.

    Critical: failure here aborts startup because the application cannot guarantee schema correctness.
    The caller holds :func:`migration_lock`.

    Raises:
        RuntimeError: When the database is older than the v0.21 head; nothing has been written to it.
    """
    alembic_cfg = Config("alembic.ini")
    with engine.connect() as connection:
        require_v0_21_or_newer(connection, ScriptDirectory.from_config(alembic_cfg))
    # Disable Alembic's own logger configuration to avoid conflicts with FastAPI / our main logger.
    alembic_cfg.attributes["configure_logger"] = False
    command.upgrade(alembic_cfg, "head")


def bootstrap_substrate_schema(engine: Engine) -> None:
    """Adopt, upgrade, and verify the substrate's migration history.

    ``event_log``, ``event_outbox`` and ``processing_jobs`` are created by this
    application's historical Alembic revisions. JASIL validates that complete,
    unversioned legacy schema against its installed migration head before
    adopting it. Empty databases are left for JASIL's upgrade to create, while
    already-versioned databases continue through the normal upgrade path.

    Must run after the application's own Alembic upgrade, which is what creates
    or normalises any legacy tables being adopted.

    Args:
        engine: The engine of the database to bootstrap.
    """
    if jasil_migrations.adopt_existing_schema(engine):
        logger.info("Adopted existing substrate tables", extra=core_logger.context(console=True))
    jasil_migrations.upgrade(engine)
    jasil_migrations.verify_schema_current(engine)


async def check_migrations() -> None:
    """
    Check for pending custom migration records.

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
