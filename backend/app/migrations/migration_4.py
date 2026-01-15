from sqlalchemy.orm import Session

import users.user.crud as user_crud

import migrations.crud as migrations_crud

import core.logger as core_logger


def process_migration_4(db: Session):
    core_logger.print_to_log_and_console("Started migration 4")

    users_processed_with_no_errors = True

    users = user_crud.get_all_users(db)

    if users:
        for user in users:
            try:
                photo_old_path = user.photo_path
                if photo_old_path:
                    user.photo_path = "data/" + photo_old_path

                user_crud.update_user_photo(user.id, db, user.photo_path)
            except Exception as err:
                core_logger.print_to_log_and_console(
                    f"Migration 4 - Error processing user {user.id}: {err}",
                    "error",
                    exc=err,
                )
                users_processed_with_no_errors = False
                continue

    # Mark migration as executed
    if users_processed_with_no_errors:
        try:
            migrations_crud.set_migration_as_executed(4, db)
        except Exception as err:
            core_logger.print_to_log_and_console(
                f"Migration 4 - Failed to set migration as executed: {err}",
                "error",
                exc=err,
            )
            return
    else:
        core_logger.print_to_log_and_console(
            "Migration 4 failed to process all users. Will try again later.",
            "error",
        )

    core_logger.print_to_log_and_console("Finished migration 4")
