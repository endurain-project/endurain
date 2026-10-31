"""Migration execution orchestration utilities."""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from sqlalchemy.orm import Session

import core.logger as core_logger
import migrations.crud as migrations_crud
import migrations.migration_1 as migrations_migration_1
import migrations.migration_2 as migrations_migration_2
import migrations.migration_3 as migrations_migration_3
import migrations.migration_4 as migrations_migration_4
import migrations.migration_5 as migrations_migration_5
import migrations.migration_6 as migrations_migration_6
import migrations.migration_8 as migrations_migration_8
import migrations.migration_9 as migrations_migration_9
import migrations.migration_10 as migrations_migration_10
import migrations.migration_11 as migrations_migration_11

logger = core_logger.get_logger(__name__)

# Synchronous migration handlers keyed by migration ID. Migration 7 (stored HR zone
# backfill) is gone: zones are computed when a stream is served.
_SYNC_MIGRATIONS: dict[int, Callable[[Session], None]] = {
    1: migrations_migration_1.process_migration_1,
    2: migrations_migration_2.process_migration_2,
    3: migrations_migration_3.process_migration_3,
    8: migrations_migration_8.process_migration_8,
    9: migrations_migration_9.process_migration_9,
    10: migrations_migration_10.process_migration_10,
    11: migrations_migration_11.process_migration_11,
}

# Asynchronous migration handlers keyed by migration ID.
_ASYNC_MIGRATIONS: dict[int, Callable[[Session], Coroutine[Any, Any, None]]] = {
    4: migrations_migration_4.process_migration_4,
    5: migrations_migration_5.process_migration_5,
    6: migrations_migration_6.process_migration_6,
}


async def check_migrations_not_executed(
    db: Session,
) -> None:
    """
    Check and execute any pending migrations.

    Iterates over unexecuted migrations and runs each migration handler in
    order. Async handlers are awaited. Sync handlers run on a worker thread: they do
    blocking work (provider calls, file handling) that would otherwise stall the
    startup event loop, and some start an event loop of their own, which
    ``asyncio.run`` refuses to do on a thread that already runs one.

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
        elif migration.id in _ASYNC_MIGRATIONS:
            await _ASYNC_MIGRATIONS[migration.id](db)
