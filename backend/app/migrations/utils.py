"""Migration execution orchestration utilities."""

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
import migrations.migration_7 as migrations_migration_7
import migrations.migration_8 as migrations_migration_8

# Synchronous migration handlers keyed by migration ID.
_SYNC_MIGRATIONS: dict[int, Callable[[Session], None]] = {
    1: migrations_migration_1.process_migration_1,
    2: migrations_migration_2.process_migration_2,
    3: migrations_migration_3.process_migration_3,
    7: migrations_migration_7.process_migration_7,
    8: migrations_migration_8.process_migration_8,
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
    order. Sync handlers are called directly; async handlers are awaited.

    Args:
        db: Database session.

    Returns:
        None.
    """
    migrations_not_executed = migrations_crud.get_migrations_not_executed(db)

    if not migrations_not_executed:
        return

    for migration in migrations_not_executed:
        core_logger.print_to_log(f"Migration not executed: {migration.name} - Migration will be executed")

        if migration.id in _SYNC_MIGRATIONS:
            _SYNC_MIGRATIONS[migration.id](db)
        elif migration.id in _ASYNC_MIGRATIONS:
            await _ASYNC_MIGRATIONS[migration.id](db)
