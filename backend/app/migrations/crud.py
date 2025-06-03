from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import core.logger as core_logger

import migrations.models as migrations_models


def get_migrations_not_executed(db: Session):
    try:
        # Get the migrations from the database
        db_migrations = (
            db.query(migrations_models.Migration).filter(migrations_models.Migration.executed == False).all()
        )

        # Check if there are not migrations if not return None
        if not db_migrations:
            return None

        # Return the migrations
        return db_migrations
    except Exception as err:
        # Log the exception
        core_logger.print_to_log_and_console(f"Error in get_migrations_not_executed: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def set_migration_as_executed(migration_id: int, db: Session):
    try:
        # Get the migration from the database
        db_migration = (
            db.query(migrations_models.Migration)
            .filter(migrations_models.Migration.id == migration_id)
            .first()
        )

        if db_migration is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Migration not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Update the migration
        db_migration.executed = True

        # Commit the transaction
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log_and_console(f"Error in set_migration_as_executed: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
