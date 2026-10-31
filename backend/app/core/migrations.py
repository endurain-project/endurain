"""Migration consistency checks run during backend startup."""

import jasil.migrations as jasil_migrations

import core.logger as core_logger
import migrations.utils as migrations_utils
from core.database import SessionLocal, engine

logger = core_logger.get_logger(__name__)


def bootstrap_substrate_schema() -> None:
    """Adopt, upgrade, and verify the substrate's migration history.

    ``event_log``, ``event_outbox`` and ``processing_jobs`` are created by this
    application's historical Alembic revisions. JASIL validates that complete,
    unversioned legacy schema against its installed migration head before
    adopting it. Empty databases are left for JASIL's upgrade to create, while
    already-versioned databases continue through the normal upgrade path.

    Must run after the application's own Alembic upgrade, which is what creates
    or normalises any legacy tables being adopted.

    Returns:
        None.
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
