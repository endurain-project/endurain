from typing import cast, overload

from fastapi import HTTPException, status
from sqlalchemy import desc, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import modules.health.constants as health_constants
import modules.health.health_weight.models as health_weight_models
import modules.health.health_weight.schema as health_weight_schema
import modules.health.health_weight.utils as health_weight_utils
import modules.health.utils as health_utils

# Private internal helpers


@overload
def _transform_health_weight(
    health_weight: health_weight_models.HealthWeight,
) -> health_weight_schema.HealthWeightRead: ...


@overload
def _transform_health_weight(
    health_weight: list[health_weight_models.HealthWeight],
) -> list[health_weight_schema.HealthWeightRead]: ...


def _transform_health_weight(
    health_weight: health_weight_models.HealthWeight | list[health_weight_models.HealthWeight],
) -> health_weight_schema.HealthWeightRead | list[health_weight_schema.HealthWeightRead]:
    """
    Transform a health weight or list of health weights to a Pydantic schema.

    Args:
        health_weight: The health weight ORM instance or list of instances.

    Returns:
        The health weight(s) as a schema.
    """
    if isinstance(health_weight, list):
        return [health_weight_schema.HealthWeightRead.model_validate(hw) for hw in health_weight]
    return health_weight_schema.HealthWeightRead.model_validate(health_weight)


@core_decorators.handle_db_errors
def _get_health_weight_model_by_id_and_user_id_or_404(
    health_weight_id: int, user_id: int, db: Session
) -> health_weight_models.HealthWeight:
    """
    Retrieve health weight record model by ID and user ID.

    Args:
        health_weight_id: Health weight record ID to fetch.
        user_id: User ID to fetch record for.
        db: Database session.

    Returns:
        Mapped ``HealthWeight`` ORM instance.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the health_weight from the database
    stmt = select(health_weight_models.HealthWeight).where(
        health_weight_models.HealthWeight.id == health_weight_id,
        health_weight_models.HealthWeight.user_id == user_id,
    )
    db_health_weight = db.execute(stmt).scalar_one_or_none()

    if db_health_weight is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health weight not found",
        )

    return db_health_weight


# Public CRUD functions


@core_decorators.handle_db_errors
def get_all_health_weight(
    db: Session,
) -> list[health_weight_schema.HealthWeightRead]:
    """
    Retrieve all health weight records from the database.

    Args:
        db: Database session.

    Returns:
        List of HealthWeightRead schemas ordered by date descending.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the health_weight from the database
    stmt = select(health_weight_models.HealthWeight).order_by(desc(health_weight_models.HealthWeight.date))
    db_health_weights = db.execute(stmt).scalars().all()
    return _transform_health_weight(list(db_health_weights))


@core_decorators.handle_db_errors
def get_health_weight_number_by_user_id(
    user_id: int, db: Session, interval: health_constants.Interval | None = None
) -> int:
    """
    Retrieve total count of health weight records for a user. If interval is
    provided, count only records starting from the calculated start date.

    Args:
        user_id: User ID to count records for.
        db: Database session.
        interval: Optional filter by goal interval.

    Returns:
        Total number of health weight records.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the number of health_weight from the database
    stmt = (
        select(func.count())
        .select_from(health_weight_models.HealthWeight)
        .where(health_weight_models.HealthWeight.user_id == user_id)
    )

    if interval is not None:
        stmt = stmt.where(
            health_weight_models.HealthWeight.date >= health_utils.get_start_date_for_interval(interval.value)
        )

    return db.execute(stmt).scalar_one()


@core_decorators.handle_db_errors
def get_all_health_weight_by_user_id(user_id: int, db: Session) -> list[health_weight_schema.HealthWeightRead]:
    """
    Retrieve all health weight records for a user.

    Args:
        user_id: User ID to fetch records for.
        db: Database session.

    Returns:
        List of HealthWeightRead schemas ordered by date descending.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the health_weight from the database
    stmt = (
        select(health_weight_models.HealthWeight)
        .where(health_weight_models.HealthWeight.user_id == user_id)
        .order_by(desc(health_weight_models.HealthWeight.date))
    )

    db_health_weights = db.execute(stmt).scalars().all()

    return _transform_health_weight(list(db_health_weights))


@core_decorators.handle_db_errors
def get_health_weight_by_user_id(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    interval: health_constants.Interval | None = None,
) -> list[health_weight_schema.HealthWeightRead]:
    """
    Retrieve health weight records for a specific user with optional pagination
        and filtering.

    Args:
        user_id (int): The ID of the user whose health weight records are to be
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
        list[health_weight_models.HealthWeight]: A list of health weight
            records sorted by date in descending order, optionally paginated.
    """
    # Get the health_weight from the database
    stmt = select(health_weight_models.HealthWeight).where(health_weight_models.HealthWeight.user_id == user_id)

    if interval is not None:
        stmt = stmt.where(
            health_weight_models.HealthWeight.date >= health_utils.get_start_date_for_interval(interval.value)
        )

    stmt = stmt.order_by(desc(health_weight_models.HealthWeight.date))

    if page_number is not None and num_records is not None:
        stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)

    db_health_weights = db.execute(stmt).scalars().all()

    return _transform_health_weight(list(db_health_weights))


@core_decorators.handle_db_errors
def get_health_weight_by_date_and_user_id(
    user_id: int, date: str, db: Session
) -> health_weight_schema.HealthWeightRead | None:
    """
    Retrieve health weight record for a user on a specific date.

    Args:
        user_id: User ID.
        date: Date string for the weight record.
        db: Database session.

    Returns:
        HealthWeightRead schema if found, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the health_weight from the database
    stmt = select(health_weight_models.HealthWeight).where(
        health_weight_models.HealthWeight.date == func.date(date),
        health_weight_models.HealthWeight.user_id == user_id,
    )

    db_health_weight = db.execute(stmt).scalar_one_or_none()

    return _transform_health_weight(db_health_weight) if db_health_weight else None


@core_decorators.handle_db_errors
def get_latest_weight_by_user_id(user_id: int, db: Session) -> health_weight_schema.HealthWeightRead | None:
    """
    Get most recent weight record for dashboard display.

    Args:
        user_id: User ID to fetch latest weight for.
        db: Database session.

    Returns:
        HealthWeightRead schema if found, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = (
        select(health_weight_models.HealthWeight)
        .where(health_weight_models.HealthWeight.user_id == user_id)
        .order_by(desc(health_weight_models.HealthWeight.date))
        .limit(1)
    )
    db_health_weight = db.execute(stmt).scalar_one_or_none()
    return _transform_health_weight(db_health_weight) if db_health_weight else None


@core_decorators.handle_db_errors
def create_health_weight(
    user_id: int, health_weight: health_weight_schema.HealthWeightCreate, db: Session
) -> health_weight_schema.HealthWeightRead:
    """
    Create a new health weight entry for a user.

    This function creates a new health weight record in the database. If the date is not provided,
    it defaults to the current date. If BMI is not provided, it is automatically calculated
    using the user's height and the provided weight.

    Args:
        user_id (int): The ID of the user for whom the health weight entry is being created.
        health_weight (health_weight_schema.HealthWeightCreate): The health weight data to be created,
            containing fields such as weight, date, and optionally BMI.
        db (Session): The database session used for database operations.

    Returns:
        health_weight_schema.HealthWeightRead: The created health weight schema instance.

    Raises:
        HTTPException:
            - 409 Conflict: If a duplicate entry exists for the same date.
            - 500 Internal Server Error: If any other unexpected error occurs during creation.

    Note:
        - The function automatically sets the date to current timestamp if not provided.
        - BMI is calculated automatically if not provided in the input.
        - The database transaction is rolled back in case of any errors.
    """
    try:
        # Check if bmi is None
        if health_weight.bmi is None:
            health_weight = cast(
                health_weight_schema.HealthWeightCreate,
                health_weight_utils.calculate_bmi(health_weight, user_id, db),
            )

        # Create a new health_weight
        db_health_weight = health_weight_models.HealthWeight(
            **health_weight.model_dump(exclude_none=False),
            user_id=user_id,
        )

        # Add the health_weight to the database
        db.add(db_health_weight)
        db.commit()
        db.refresh(db_health_weight)

        # Return the health_weight
        return _transform_health_weight(db_health_weight)
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate entry error. Check if there is already a entry created for {health_weight.date}",
        ) from integrity_error


@core_decorators.handle_db_errors
def edit_health_weight(
    user_id: int,
    health_weight: health_weight_schema.HealthWeightUpdate,
    db: Session,
) -> health_weight_schema.HealthWeightRead:
    """
    Edit an existing health weight record for a user.

    Args:
        user_id: User ID who owns the health weight record.
        health_weight: Health weight data to update.
        db: Database session.

    Returns:
        Updated health weight schema instance.

    Raises:
        HTTPException: If record not found or database error.
    """
    # Ensure the health_weight belongs to the user
    if health_weight.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot edit health weight for another user.",
        )

    # Get the health_weight from the database
    db_health_weight = _get_health_weight_model_by_id_and_user_id_or_404(health_weight.id, user_id, db)

    # Check if bmi is None
    if health_weight.bmi is None and health_weight.weight is not None:
        health_weight = cast(
            health_weight_schema.HealthWeightUpdate,
            health_weight_utils.calculate_bmi(health_weight, user_id, db),
        )

    # Dictionary of fields to update if they are not None
    health_weight_data = health_weight.model_dump(exclude_unset=True)
    # Iterate over the fields and update dynamically
    for key, value in health_weight_data.items():
        setattr(db_health_weight, key, value)

    # Commit the transaction and refresh
    db.commit()
    db.refresh(db_health_weight)

    return _transform_health_weight(db_health_weight)


@core_decorators.handle_db_errors
def recalculate_bmi_for_user(user_id: int, height_cm: float | None, db: Session) -> None:
    """
    Recalculate BMI for all of a user's weight entries in one statement.

    Issues a single bulk UPDATE rather than loading and saving each
    record individually, keeping the work to a constant number of
    database round trips regardless of how many entries exist.

    Args:
        user_id: User ID whose weight entries should be updated.
        height_cm: User height in centimeters, or None if unknown.
        db: Database session.

    Returns:
        None

    Raises:
        HTTPException: If database error occurs.
    """
    if height_cm and height_cm > 0:
        # bmi = weight (kg) / (height (m))^2
        new_bmi = health_weight_models.HealthWeight.weight / (height_cm / 100.0) ** 2
    else:
        # Without a usable height, BMI cannot be derived, so clear it.
        new_bmi = None

    stmt = (
        update(health_weight_models.HealthWeight)
        .where(health_weight_models.HealthWeight.user_id == user_id)
        .values(bmi=new_bmi)
    )

    db.execute(stmt)
    db.commit()


@core_decorators.handle_db_errors
def delete_health_weight(user_id: int, health_weight_id: int, db: Session) -> None:
    """
    Delete a health weight record for a user.

    Args:
        user_id: User ID who owns the health weight record.
        health_weight_id: Health weight record ID to delete.
        db: Database session.

    Returns:
        None

    Raises:
        HTTPException: If record not found or database error.
    """
    # Get and delete the health_weight
    db_health_weight = _get_health_weight_model_by_id_and_user_id_or_404(health_weight_id, user_id, db)

    # Delete the record
    db.delete(db_health_weight)
    db.commit()
