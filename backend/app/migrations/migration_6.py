"""Migration 6: lowercase usernames and normalise birthdates."""

from sqlalchemy.orm import Session

import core.logger as core_logger
import migrations.crud as migrations_crud
import modules.users.users.crud as user_crud
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
        users = user_crud.get_all_users(db)
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

                await user_crud.edit_user(user.id, user_converted, db)
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
            migrations_crud.set_migration_as_executed(6, db)
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
