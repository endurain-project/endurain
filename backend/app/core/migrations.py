import migrations.utils as migrations_utils

import core.logger as core_logger

from core.database import SessionLocal


def check_migrations():
    core_logger.print_to_log_and_console("Checking for migrations not executed")

    # Create a new database session
    db = SessionLocal()
    try:
        # Check migrations not executed
        migrations_utils.check_migrations_not_executed(db)
    finally:
        # Ensure the session is closed after use
        db.close()

        core_logger.print_to_log_and_console("Migration check completed")
