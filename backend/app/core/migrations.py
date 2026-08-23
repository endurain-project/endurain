"""Migration consistency checks run during backend startup."""

import jasil.migrations as jasil_migrations
import jasil.orm as jasil_orm
import sqlalchemy as sa

import core.logger as core_logger
import migrations.utils as migrations_utils
from core.database import SessionLocal, engine

logger = core_logger.get_logger(__name__)

#: The JASIL revision whose schema this application's own Alembic history already
#: creates. Everything after it is the substrate's to apply.
SUBSTRATE_BASELINE_REVISION = "rev0001"


def substrate_tables_exist() -> bool:
    """Return whether every table the substrate owns is already present."""
    inspector = sa.inspect(engine)
    return all(inspector.has_table(name) for name in jasil_orm.jasil_table_names())


def bootstrap_substrate_schema() -> None:
    """Adopt the substrate's tables into its own migration history, then upgrade.

    ``event_log``, ``event_outbox`` and ``processing_jobs`` are created by this
    application's own Alembic history (v0_19_0, refined in v0_20_0) at exactly
    the shape of the substrate's baseline revision. That holds for a fresh
    database as much as an existing one, because those revisions stay in the
    history forever, so on first boot after adopting JASIL both look the same:
    the tables are there and the substrate's version table is not.

    Stamping the *baseline* rather than head is what records that accurately. A
    later JASIL release's revisions then still apply on the next boot, instead
    of being skipped as though they had already run.

    Must run after the application's own Alembic upgrade, which is what creates
    the tables being adopted.

    Returns:
        None.
    """
    if jasil_migrations.db_revision(engine) is None and substrate_tables_exist():
        logger.info(
            f"Adopting existing substrate tables at {SUBSTRATE_BASELINE_REVISION}",
            extra=core_logger.context(console=True),
        )
        jasil_migrations.stamp(engine, SUBSTRATE_BASELINE_REVISION)
    jasil_migrations.upgrade(engine)


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
