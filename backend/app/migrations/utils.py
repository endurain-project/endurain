"""Migration execution orchestration utilities."""

import asyncio
from collections.abc import Callable

from sqlalchemy.orm import Session

import core.logger as core_logger
import migrations.crud as migrations_crud
import migrations.migration_11 as migrations_migration_11
import migrations.migration_12 as migrations_migration_12
import migrations.migration_13 as migrations_migration_13
import migrations.migration_14 as migrations_migration_14

logger = core_logger.get_logger(__name__)

# Migration handlers keyed by migration ID. A migration ID with no handler is skipped.
_SYNC_MIGRATIONS: dict[int, Callable[[Session], None]] = {
    11: migrations_migration_11.process_migration_11,
    12: migrations_migration_12.process_migration_12,
    13: migrations_migration_13.process_migration_13,
    14: migrations_migration_14.process_migration_14,
}


async def check_migrations_not_executed(
    db: Session,
) -> None:
    """
    Check and execute any pending migrations.

    Iterates over unexecuted migrations and runs each migration handler in
    order. Handlers run on a worker thread: they do
    blocking work (provider calls, file handling) that would otherwise stall the
    startup event loop, and the file validators refuse a thread that runs one.

    Args:
        db: Database session.

    Returns:
        None.
    """
    migrations_not_executed = migrations_crud.get_migrations_not_executed(db)

    if not migrations_not_executed:
        return

    for migration in migrations_not_executed:
        logger.info("Migration not executed; it will be executed", extra=core_logger.context(migration=migration.name))

        if migration.id in _SYNC_MIGRATIONS:
            await asyncio.to_thread(_SYNC_MIGRATIONS[migration.id], db)
