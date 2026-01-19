from sqlalchemy.orm import Session

import core.logger as core_logger

import migrations.crud as migrations_crud

import users.users.crud as user_crud
import users.users.schema as users_schema


async def process_migration_6(db: Session):
    core_logger.print_to_log_and_console("Started migration 6")

    users_processed_with_no_errors = True

    try:
        users = user_crud.get_all_users(db)
    except Exception as err:
        core_logger.print_to_log_and_console(
            f"Migration 6 - Error fetching users: {err}",
            "error",
            exc=err,
        )
        users_processed_with_no_errors = False

    if users:
        for user in users:
            try:
                user.username = user.username.lower()
                if user.birthdate:
                    user.birthdate = user.birthdate.isoformat()
                user_converted = users_schema.UsersRead.model_validate(user)

                await user_crud.edit_user(user.id, user_converted, db)
            except Exception as err:
                core_logger.print_to_log_and_console(
                    f"Migration 6 - Error processing user {user.id}: {err}",
                    "error",
                    exc=err,
                )
                users_processed_with_no_errors = False
                continue

    # Mark migration as executed
    if users_processed_with_no_errors:
        try:
            migrations_crud.set_migration_as_executed(6, db)
        except Exception as err:
            core_logger.print_to_log_and_console(
                f"Migration 6 - Failed to set migration as executed: {err}",
                "error",
                exc=err,
            )
            return
    else:
        core_logger.print_to_log_and_console(
            "Migration 6 failed to process all users. Will try again later.",
            "error",
        )

    core_logger.print_to_log_and_console("Finished migration 6")
