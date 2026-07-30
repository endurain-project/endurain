"""Migration consistency checks run during backend startup."""

import core.logger as core_logger
import migrations.utils as migrations_utils
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)


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
