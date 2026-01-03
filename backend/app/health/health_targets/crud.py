from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import health.health_targets.models as health_targets_models
import health.health_targets.schema as health_targets_schema

import core.logger as core_logger


def get_health_targets_by_user_id(
    user_id: int, db: Session
) -> health_targets_models.HealthTargets | None:
    try:
        # Get the health_targets from the database
        return (
            db.query(health_targets_models.HealthTargets)
            .filter(health_targets_models.HealthTargets.user_id == user_id)
            .first()
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_health_targets_by_user_id: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_health_targets(
    user_id: int, db: Session
) -> health_targets_schema.HealthTargets:
    try:
        # Create a new health_target
        db_health_targets = health_targets_models.HealthTargets(
            user_id=user_id,
            weight=None,
        )

        # Add the health_targets to the database
        db.add(db_health_targets)
        db.commit()
        db.refresh(db_health_targets)

        health_targets = health_targets_schema.HealthTargets(
            id=db_health_targets.id,
            user_id=user_id,
        )

        # Return the health_targets
        return health_targets
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate entry error. Check if there is already an entry created for the user",
        ) from integrity_error
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in create_health_targets: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def edit_health_target(
    health_target: health_targets_schema.HealthTargets,
    user_id: int,
    db: Session,
) -> health_targets_models.HealthTargets:
    try:
        # Get the user health target from the database
        db_health_target = (
            db.query(health_targets_models.HealthTargets)
            .filter(
                health_targets_models.HealthTargets.user_id == user_id,
            )
            .first()
        )

        if db_health_target is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User health target not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Dictionary of the fields to update if they are not None
        health_target_data = health_target.model_dump(exclude_unset=True)
        # Iterate over the fields and update the db_user dynamically
        for key, value in health_target_data.items():
            setattr(db_health_target, key, value)

        # Commit the transaction
        db.commit()

        return db_health_target
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in edit_health_target: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error: {err}",
        ) from err
