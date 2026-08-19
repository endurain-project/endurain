"""Migration 5: prefix photo and media paths with '/app/backend/'."""

from sqlalchemy.orm import Session

import core.logger as core_logger
import migrations.crud as migrations_crud
import modules.activities.activity_media.migration_service as activity_media_crud
import modules.users.users.crud as user_crud

logger = core_logger.get_logger(__name__)


async def process_migration_5(db: Session) -> None:
    """
    Run migration 5: prefix paths with '/app/backend/'.

    Args:
        db: The SQLAlchemy database session.

    Returns:
        None

    Raises:
        Exception: Logs errors per-record; does not re-raise.
    """
    logger.info("Started migration 5", extra=core_logger.context(console=True))

    users_processed_with_no_errors = True
    activity_media_processed_with_no_errors = True

    users = user_crud.get_all_users(db)
    activity_media = activity_media_crud.get_all_activity_media(db)

    if users:
        for user in users:
            try:
                photo_old_path = user.photo_path
                new_photo_path = "/app/backend/" + photo_old_path if photo_old_path else None
                await user_crud.update_user_photo(user.id, db, new_photo_path)
            except Exception as err:
                logger.error(
                    f"Migration 5 - Error processing user {user.id}: {err}",
                    exc_info=err,
                    extra=core_logger.context(console=True),
                )
                users_processed_with_no_errors = False
                continue

    if activity_media:
        for media in activity_media:
            try:
                new_media_path = f"/app/backend/{media.media_path}"
                activity_media_crud.edit_activity_media_media_path(media.id, new_media_path, db)
            except Exception as err:
                logger.error(
                    f"Migration 5 - Error processing activity media {media.id}: {err}",
                    exc_info=err,
                    extra=core_logger.context(console=True),
                )
                activity_media_processed_with_no_errors = False
                continue

    # Mark migration as executed
    if users_processed_with_no_errors and activity_media_processed_with_no_errors:
        try:
            migrations_crud.set_migration_as_executed(5, db)
        except Exception as err:
            logger.error(
                f"Migration 5 - Failed to set migration as executed: {err}",
                exc_info=err,
                extra=core_logger.context(console=True),
            )
            return
    else:
        logger.error(
            "Migration 5 failed to process all users and/or activity media. Will try again later.",
            extra=core_logger.context(console=True),
        )

    logger.info("Finished migration 5", extra=core_logger.context(console=True))
