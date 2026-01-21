import migrations.utils as migrations_utils

import core.logger as core_logger

from core.database import SessionLocal


async def check_migrations():
    core_logger.print_to_log_and_console("Checking for migrations not executed")

    # Create a new database session using context manager
    with SessionLocal() as db:
        try:
            # Check migrations not executed
            await migrations_utils.check_migrations_not_executed(db)

            core_logger.print_to_log_and_console("Migration check completed")
        except Exception as err:
            raise err
