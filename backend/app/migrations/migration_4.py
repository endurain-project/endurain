"""Migration 4: prefix user photo paths with 'data/'."""

from sqlalchemy.orm import Session

import core.logger as core_logger
import migrations.crud as migrations_crud
import modules.users.users.crud as user_crud

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

    users = user_crud.get_all_users(db)

    if users:
        for user in users:
            try:
                photo_old_path = user.photo_path
                new_photo_path = "data/" + photo_old_path if photo_old_path else None
                await user_crud.update_user_photo(user.id, db, new_photo_path)
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
            migrations_crud.set_migration_as_executed(4, db)
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
