from sqlalchemy.orm import Session

import activities.activity_media.crud as activity_media_crud

import core.logger as core_logger

import migrations.crud as migrations_crud

import users.user.crud as user_crud


async def process_migration_5(db: Session):
    core_logger.print_to_log_and_console("Started migration 5")

    users_processed_with_no_errors = True
    activity_media_processed_with_no_errors = True

    users = user_crud.get_all_users(db)
    activity_media = activity_media_crud.get_all_activity_media(db)

    if users:
        for user in users:
            try:
                photo_old_path = user.photo_path
                if photo_old_path:
                    user.photo_path = "/app/backend/" + photo_old_path

                await user_crud.update_user_photo(user.id, db, user.photo_path)
            except Exception as err:
                core_logger.print_to_log_and_console(
                    f"Migration 5 - Error processing user {user.id}: {err}",
                    "error",
                    exc=err,
                )
                users_processed_with_no_errors = False
                continue

    if activity_media:
        for media in activity_media:
            try:
                media.media_path = "/app/backend/" + media.media_path
                activity_media_crud.edit_activity_media_media_path(
                    media.id, media.media_path, db
                )
            except Exception as err:
                core_logger.print_to_log_and_console(
                    f"Migration 5 - Error processing activity media {media.id}: {err}",
                    "error",
                    exc=err,
                )
                activity_media_processed_with_no_errors = False
                continue

    # Mark migration as executed
    if users_processed_with_no_errors and activity_media_processed_with_no_errors:
        try:
            migrations_crud.set_migration_as_executed(5, db)
        except Exception as err:
            core_logger.print_to_log_and_console(
                f"Migration 5 - Failed to set migration as executed: {err}",
                "error",
                exc=err,
            )
            return
    else:
        core_logger.print_to_log_and_console(
            "Migration 5 failed to process all users and/or activity media. Will try again later.",
            "error",
        )

    core_logger.print_to_log_and_console("Finished migration 5")
