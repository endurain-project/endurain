"""Migration 4: prefix user photo paths with 'data/'."""

from sqlalchemy.orm import Session

import core.logger as core_logger
import migrations.service as migrations_service
import modules.users.users.migration_service as users_migration

logger = core_logger.get_logger(__name__)


async def process_migration_4(db: Session) -> None:
    """
    Run migration 4: prefix photo paths with 'data/'.

    Args:
        db: The SQLAlchemy database session.

    Returns:
        None

    Raises:
        Exception: Logs errors per-user; does not re-raise.
    """
    logger.info("Started migration 4", extra=core_logger.context(console=True))

    users_processed_with_no_errors = True

    users = users_migration.list_users(db)

    if users:
        for user in users:
            try:
                photo_old_path = user.photo_path
                new_photo_path = "data/" + photo_old_path if photo_old_path else None
                users_migration.set_photo_key(user.id, new_photo_path, db)
            except Exception as err:
                logger.error(
                    f"Migration 4 - Error processing user {user.id}: {err}",
                    exc_info=err,
                    extra=core_logger.context(console=True),
                )
                users_processed_with_no_errors = False
                continue

    # Mark migration as executed
    if users_processed_with_no_errors:
        try:
            migrations_service.mark_executed(4, db)
        except Exception as err:
            logger.error(
                f"Migration 4 - Failed to set migration as executed: {err}",
                exc_info=err,
                extra=core_logger.context(console=True),
            )
            return
    else:
        logger.error(
            "Migration 4 failed to process all users. Will try again later.", extra=core_logger.context(console=True)
        )

    logger.info("Finished migration 4", extra=core_logger.context(console=True))
