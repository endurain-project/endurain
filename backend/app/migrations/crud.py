import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import models

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


def get_migrations_not_executed(
    db: Session
):
    try:
        # Get the migrations from the database
        db_migrations = (
            db.query(models.Migration)
            .filter(models.Migration.executed == False)
            .all()
        )

        # Check if there are not migrations if not return None
        if not db_migrations:
            return None

        # Return the migrations
        return db_migrations
    except Exception as err:
        # Log the exception
        logger.error(f"Error in get_migrations_not_executed: {err}", exc_info=True)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
    

def set_migration_as_executed(migration_id: int, db: Session):
    try:
        # Get the migration from the database
        db_migration = (
            db.query(models.Migration)
            .filter(models.Migration.id == migration_id)
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
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        logger.error(f"Error in set_migration_as_executed: {err}", exc_info=True)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err