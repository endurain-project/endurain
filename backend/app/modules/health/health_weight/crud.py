"""CRUD operations for health weight records."""

from datetime import date as date_type

from sqlalchemy import desc, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.health.health_weight.models as health_weight_models
import modules.health.health_weight.schema as health_weight_schema
import modules.health.health_weight.serializers as health_weight_serializers


def _get_model_by_id_and_user_id(health_weight_id: int, user_id: int, db: Session) -> health_weight_models.HealthWeight:
    """Load a user's weight row by id.

    Args:
        health_weight_id: The record to load.
        user_id: The record's owner.
        db: Database session.

    Returns:
        The ORM row.

    Raises:
        NotFoundError: If the user has no such record.
    """
    stmt = select(health_weight_models.HealthWeight).where(
        health_weight_models.HealthWeight.id == health_weight_id,
        health_weight_models.HealthWeight.user_id == user_id,
    )
    db_health_weight = db.execute(stmt).scalar_one_or_none()

    if db_health_weight is None:
        raise core_exceptions.NotFoundError("Health weight not found")

    return db_health_weight


def get_all_health_weight(db: Session) -> list[health_weight_schema.HealthWeightRead]:
    """Retrieve every weight record of every user (migration use only).

    Args:
        db: Database session.

    Returns:
        The records ordered by date descending.
    """
    stmt = select(health_weight_models.HealthWeight).order_by(desc(health_weight_models.HealthWeight.date))
    return health_weight_serializers.to_read_schemas(list(db.execute(stmt).scalars().all()))


def get_health_weight_number_by_user_id(user_id: int, db: Session, since: date_type | None = None) -> int:
    """Count a user's weight records.

    Args:
        user_id: The records' owner.
        db: Database session.
        since: Count only records on or after this date.

    Returns:
        The number of records.
    """
    stmt = (
        select(func.count())
        .select_from(health_weight_models.HealthWeight)
        .where(health_weight_models.HealthWeight.user_id == user_id)
    )
    if since is not None:
        stmt = stmt.where(health_weight_models.HealthWeight.date >= since)

    return db.execute(stmt).scalar_one()


def get_all_health_weight_by_user_id(user_id: int, db: Session) -> list[health_weight_schema.HealthWeightRead]:
    """Retrieve all of a user's weight records.

    Args:
        user_id: The records' owner.
        db: Database session.

    Returns:
        The records ordered by date descending.
    """
    stmt = (
        select(health_weight_models.HealthWeight)
        .where(health_weight_models.HealthWeight.user_id == user_id)
        .order_by(desc(health_weight_models.HealthWeight.date))
    )
    return health_weight_serializers.to_read_schemas(list(db.execute(stmt).scalars().all()))


def get_health_weight_by_user_id(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    since: date_type | None = None,
) -> list[health_weight_schema.HealthWeightRead]:
    """Retrieve a user's weight records, optionally paginated and bounded.

    Args:
        user_id: The records' owner.
        db: Database session.
        page_number: 1-based page; paginates only together with ``num_records``.
        num_records: Records per page.
        since: Return only records on or after this date.

    Returns:
        The records ordered by date descending.
    """
    stmt = select(health_weight_models.HealthWeight).where(health_weight_models.HealthWeight.user_id == user_id)

    if since is not None:
        stmt = stmt.where(health_weight_models.HealthWeight.date >= since)

    stmt = stmt.order_by(desc(health_weight_models.HealthWeight.date))

    if page_number is not None and num_records is not None:
        stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)

    return health_weight_serializers.to_read_schemas(list(db.execute(stmt).scalars().all()))


def get_health_weight_by_date_and_user_id(
    user_id: int, date: str, db: Session
) -> health_weight_schema.HealthWeightRead | None:
    """Retrieve a user's weight record for a date.

    Args:
        user_id: The record's owner.
        date: The record's date.
        db: Database session.

    Returns:
        The record, or ``None``.
    """
    stmt = select(health_weight_models.HealthWeight).where(
        health_weight_models.HealthWeight.date == func.date(date),
        health_weight_models.HealthWeight.user_id == user_id,
    )
    db_health_weight = db.execute(stmt).scalar_one_or_none()

    return health_weight_serializers.to_read_schema(db_health_weight) if db_health_weight else None


def get_latest_weight_by_user_id(user_id: int, db: Session) -> health_weight_schema.HealthWeightRead | None:
    """Retrieve a user's most recent weight record.

    Args:
        user_id: The record's owner.
        db: Database session.

    Returns:
        The latest record, or ``None``.
    """
    stmt = (
        select(health_weight_models.HealthWeight)
        .where(health_weight_models.HealthWeight.user_id == user_id)
        .order_by(desc(health_weight_models.HealthWeight.date))
        .limit(1)
    )
    db_health_weight = db.execute(stmt).scalar_one_or_none()

    return health_weight_serializers.to_read_schema(db_health_weight) if db_health_weight else None


def create_health_weight(
    user_id: int, health_weight: health_weight_schema.HealthWeightCreate, db: Session
) -> health_weight_schema.HealthWeightRead:
    """Stage a new weight record for a user.

    Args:
        user_id: The record's owner.
        health_weight: The record to create.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the user already has a record for that date.
    """
    db_health_weight = health_weight_models.HealthWeight(
        **health_weight.model_dump(exclude_none=False),
        user_id=user_id,
    )

    try:
        db.add(db_health_weight)
        db.flush()
        db.refresh(db_health_weight)
    except IntegrityError as err:
        raise core_exceptions.ConflictError(
            f"Duplicate entry error. Check if there is already a entry created for {health_weight.date}"
        ) from err

    return health_weight_serializers.to_read_schema(db_health_weight)


def edit_health_weight(
    user_id: int,
    health_weight: health_weight_schema.HealthWeightUpdate,
    db: Session,
) -> health_weight_schema.HealthWeightRead:
    """Stage an update to a user's weight record.

    Args:
        user_id: The record's owner.
        health_weight: The record with its changes.
        db: Database session.

    Returns:
        The updated record.

    Raises:
        NotFoundError: If the user has no such record.
    """
    db_health_weight = _get_model_by_id_and_user_id(health_weight.id, user_id, db)

    for key, value in health_weight.model_dump(exclude_unset=True).items():
        setattr(db_health_weight, key, value)

    db.flush()
    db.refresh(db_health_weight)

    return health_weight_serializers.to_read_schema(db_health_weight)


def recalculate_bmi_for_user(user_id: int, height_cm: float | None, db: Session) -> None:
    """Stage a BMI recalculation for all of a user's weight records in one statement.

    A single bulk UPDATE keeps the work to a constant number of round trips
    regardless of how many records exist.

    Args:
        user_id: The records' owner.
        height_cm: The user's height in centimeters, or ``None`` if unknown.
        db: Database session.
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
    db.flush()


def delete_health_weight(user_id: int, health_weight_id: int, db: Session) -> None:
    """Stage the deletion of a user's weight record.

    Args:
        user_id: The record's owner.
        health_weight_id: The record to delete.
        db: Database session.

    Raises:
        NotFoundError: If the user has no such record.
    """
    db.delete(_get_model_by_id_and_user_id(health_weight_id, user_id, db))
    db.flush()
