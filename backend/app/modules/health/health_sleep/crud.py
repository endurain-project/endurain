from typing import overload

from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import modules.health.constants as health_constants
import modules.health.health_sleep.models as health_sleep_models
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.utils as health_utils

# Private internal helpers


@overload
def _transform_health_sleep(health_sleep: health_sleep_models.HealthSleep) -> health_sleep_schema.HealthSleepRead: ...


@overload
def _transform_health_sleep(
    health_sleep: list[health_sleep_models.HealthSleep],
) -> list[health_sleep_schema.HealthSleepRead]: ...


def _transform_health_sleep(
    health_sleep: health_sleep_models.HealthSleep | list[health_sleep_models.HealthSleep],
) -> health_sleep_schema.HealthSleepRead | list[health_sleep_schema.HealthSleepRead]:
    """
    Transform a health sleep or list of health sleep to a Pydantic schema.

    Args:
        health_sleep: The health sleep ORM instance or list of instances.

    Returns:
        The health sleep(s) as a schema.
    """
    if isinstance(health_sleep, list):
        return [health_sleep_schema.HealthSleepRead.model_validate(hw) for hw in health_sleep]
    return health_sleep_schema.HealthSleepRead.model_validate(health_sleep)


@core_decorators.handle_db_errors
def _get_health_sleep_model_by_id_and_user_id_or_404(
    health_sleep_id: int, user_id: int, db: Session
) -> health_sleep_models.HealthSleep:
    """
    Retrieve health sleep record model by ID and user ID.

    Args:
        health_sleep_id: Health sleep record ID to fetch.
        user_id: User ID to fetch record for.
        db: Database session.

    Returns:
        Mapped ``HealthSleep`` ORM instance.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the health_sleep from the database
    stmt = select(health_sleep_models.HealthSleep).where(
        health_sleep_models.HealthSleep.id == health_sleep_id,
        health_sleep_models.HealthSleep.user_id == user_id,
    )
    db_health_sleep = db.execute(stmt).scalar_one_or_none()

    if db_health_sleep is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health sleep not found",
        )

    return db_health_sleep


# Public CRUD functions


@core_decorators.handle_db_errors
def get_health_sleep_number_by_user_id(
    user_id: int, db: Session, interval: health_constants.Interval | None = None
) -> int:
    """
    Retrieve total count of health sleep records for a user. If interval is
    provided, count only records starting from the calculated start date.

    Args:
        user_id: User ID to count records for.
        db: Database session.
        interval: Optional filter by goal interval.

    Returns:
        Total number of health sleep records.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the number of health_sleep from the database
    stmt = (
        select(func.count())
        .select_from(health_sleep_models.HealthSleep)
        .where(health_sleep_models.HealthSleep.user_id == user_id)
    )

    if interval is not None:
        stmt = stmt.where(
            health_sleep_models.HealthSleep.date >= health_utils.get_start_date_for_interval(interval.value)
        )

    return db.execute(stmt).scalar_one()


@core_decorators.handle_db_errors
def get_health_sleep_by_user_id(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    interval: health_constants.Interval | None = None,
) -> list[health_sleep_schema.HealthSleepRead]:
    """
    Retrieve health sleep records for a specific user with optional pagination
        and filtering.

    Args:
        user_id (int): The ID of the user whose health sleep records are to be
            retrieved.
        db (Session): The database session used to execute the query.
        page_number (int | None, optional): The page number for pagination
            (1-indexed).
            If provided, num_records must also be provided. Defaults to None.
        num_records (int | None, optional): The number of records per page.
            If provided, page_number must also be provided. Defaults to None.
        interval (health_constants.Interval | None, optional): The time
            interval to filter records.
            If provided, only records from the start of the interval to present
            are returned. Defaults to None.

    Returns:
        list[health_sleep_schema.HealthSleepRead]: A list of health sleep
            records sorted by date in descending order, optionally paginated.
    """
    # Get the health_sleep from the database
    stmt = select(health_sleep_models.HealthSleep).where(health_sleep_models.HealthSleep.user_id == user_id)

    if interval is not None:
        stmt = stmt.where(
            health_sleep_models.HealthSleep.date >= health_utils.get_start_date_for_interval(interval.value)
        )

    stmt = stmt.order_by(desc(health_sleep_models.HealthSleep.date))

    if page_number is not None and num_records is not None:
        stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)

    db_health_sleep = db.execute(stmt).scalars().all()

    return _transform_health_sleep(list(db_health_sleep))


@core_decorators.handle_db_errors
def get_health_sleep_by_date_and_user_id(
    user_id: int, date: str, db: Session
) -> health_sleep_schema.HealthSleepRead | None:
    """
    Retrieve health sleep record for a user on a specific date.

    Args:
        user_id: User ID.
        date: Date string for the sleep record.
        db: Database session.

    Returns:
        HealthSleepRead schema if found, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the health_sleep from the database
    stmt = select(health_sleep_models.HealthSleep).where(
        health_sleep_models.HealthSleep.date == func.date(date),
        health_sleep_models.HealthSleep.user_id == user_id,
    )
    db_health_sleep = db.execute(stmt).scalar_one_or_none()
    return _transform_health_sleep(db_health_sleep) if db_health_sleep else None


@core_decorators.handle_db_errors
def create_health_sleep(
    user_id: int,
    health_sleep: health_sleep_schema.HealthSleepCreate,
    db: Session,
) -> health_sleep_schema.HealthSleepRead:
    """
    Create a new health sleep record for a user.

    Args:
        user_id: User ID for the sleep record.
        health_sleep: Health sleep data to create.
        db: Database session.

    Returns:
        Created health sleep record with assigned ID.

    Raises:
        HTTPException: 409 if duplicate entry, 500 if database
            error.
    """
    try:
        # Create a new health_sleep
        db_health_sleep = health_sleep_models.HealthSleep(
            **health_sleep.model_dump(
                exclude_none=False,
                mode="json",
            ),
            user_id=user_id,
        )

        # Add the health_sleep to the database
        db.add(db_health_sleep)
        db.commit()
        db.refresh(db_health_sleep)

        # Return the created health_sleep model
        return _transform_health_sleep(db_health_sleep)
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(f"Duplicate entry error. Check if there is already an entry created for {health_sleep.date}"),
        ) from integrity_error


@core_decorators.handle_db_errors
def edit_health_sleep(
    user_id: int,
    health_sleep: health_sleep_schema.HealthSleepUpdate,
    db: Session,
) -> health_sleep_schema.HealthSleepRead:
    """
    Edit an existing health sleep record for a user.

    Args:
        user_id: User ID whose sleep record is being edited.
        health_sleep: Updated health sleep data.
        db: Database session.

    Returns:
        Updated HealthSleepRead schema.

    Raises:
        HTTPException: 403 if trying to edit other user record, 404 if not
            found, 500 if database error.
    """
    # Ensure the health_sleep belongs to the user
    if health_sleep.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot edit health sleep for another user.",
        )

    # Get the health_sleep from the database
    db_health_sleep = _get_health_sleep_model_by_id_and_user_id_or_404(health_sleep.id, user_id, db)

    # Dictionary of the fields to update if they are not None
    health_sleep_data = health_sleep.model_dump(exclude_unset=True, mode="json")
    # Iterate over fields and update dynamically
    for key, value in health_sleep_data.items():
        setattr(db_health_sleep, key, value)

    # Commit the transaction
    db.commit()
    db.refresh(db_health_sleep)

    return _transform_health_sleep(db_health_sleep)


@core_decorators.handle_db_errors
def delete_health_sleep(user_id: int, health_sleep_id: int, db: Session) -> None:
    """
    Delete a health sleep record for a specific user.

    Args:
        user_id: User ID who owns the sleep record.
        health_sleep_id: Sleep record ID to delete.
        db: Database session.

    Returns:
        None

    Raises:
        HTTPException: 404 if not found, 500 if database error.
    """
    # Get the record to delete
    db_health_sleep = _get_health_sleep_model_by_id_and_user_id_or_404(health_sleep_id, user_id, db)

    # Delete the record
    db.delete(db_health_sleep)
    db.commit()
