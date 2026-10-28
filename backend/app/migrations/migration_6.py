"""Migration 6: lowercase usernames and normalise birthdates."""

from sqlalchemy.orm import Session

import core.logger as core_logger
import migrations.service as migrations_service
import modules.users.users.migration_service as users_migration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


async def process_migration_6(db: Session) -> None:
    """
    Run migration 6: lowercase usernames and ISO-format birthdates.

    Args:
        db: The SQLAlchemy database session.

    Returns:
        None

    Raises:
        Exception: Logs errors per-user; does not re-raise.
    """
    logger.info("Started migration 6", extra=core_logger.context(console=True))

    users_processed_with_no_errors = True
    users = []

    try:
        users = users_migration.list_users(db)
    except Exception as err:
        logger.error(
            f"Migration 6 - Error fetching users: {err}", exc_info=err, extra=core_logger.context(console=True)
        )
        users_processed_with_no_errors = False

    if users:
        for user in users:
            try:
                username = user.username.lower()
                birthdate = user.birthdate.isoformat() if user.birthdate else None
                user_converted = users_schema.UsersRead.model_validate(user).model_copy(
                    update={
                        "username": username,
                        "birthdate": birthdate,
                    }
                )

                users_migration.edit_user(user.id, users_schema.UsersEdit.from_read(user_converted), db)
            except Exception as err:
                logger.error(
                    f"Migration 6 - Error processing user {user.id}: {err}",
                    exc_info=err,
                    extra=core_logger.context(console=True),
                )
                users_processed_with_no_errors = False
                continue

    # Mark migration as executed
    if users_processed_with_no_errors:
        try:
            migrations_service.mark_executed(6, db)
        except Exception as err:
            logger.error(
                f"Migration 6 - Failed to set migration as executed: {err}",
                exc_info=err,
                extra=core_logger.context(console=True),
            )
            return
    else:
        logger.error(
            "Migration 6 failed to process all users. Will try again later.", extra=core_logger.context(console=True)
        )

    logger.info("Finished migration 6", extra=core_logger.context(console=True))
