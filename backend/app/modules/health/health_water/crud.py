"""CRUD operations for health water intake records."""

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import desc, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.health.health_water.models as health_water_models
import modules.health.health_water.schema as health_water_schema
import modules.health.health_water.serializers as health_water_serializers


def _get_model_by_id_and_user_id(health_water_id: int, user_id: int, db: Session) -> health_water_models.HealthWater:
    """Load a user's water row by id.

    Args:
        health_water_id: The record to load.
        user_id: The record's owner.
        db: Database session.

    Returns:
        The ORM row.

    Raises:
        NotFoundError: If the user has no such record.
    """
    stmt = select(health_water_models.HealthWater).where(
        health_water_models.HealthWater.id == health_water_id,
        health_water_models.HealthWater.user_id == user_id,
    )
    db_health_water = db.execute(stmt).scalar_one_or_none()

    if db_health_water is None:
        raise core_exceptions.NotFoundError("Health water not found")

    return db_health_water


def get_health_water_number_by_user_id(user_id: int, db: Session, since: date_type | None = None) -> int:
    """Count a user's water intake records.

    Args:
        user_id: The records' owner.
        db: Database session.
        since: Count only records on or after this date.

    Returns:
        The number of records.
    """
    stmt = (
        select(func.count())
        .select_from(health_water_models.HealthWater)
        .where(health_water_models.HealthWater.user_id == user_id)
    )
    if since is not None:
        stmt = stmt.where(health_water_models.HealthWater.date >= since)

    return db.execute(stmt).scalar_one()


def get_health_water_by_user_id(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    since: date_type | None = None,
) -> list[health_water_schema.HealthWaterRead]:
    """Retrieve a user's water intake records, optionally paginated and bounded.

    Args:
        user_id: The records' owner.
        db: Database session.
        page_number: 1-based page; paginates only together with ``num_records``.
        num_records: Records per page.
        since: Return only records on or after this date.

    Returns:
        The records ordered by date descending.
    """
    stmt = select(health_water_models.HealthWater).where(health_water_models.HealthWater.user_id == user_id)

    if since is not None:
        stmt = stmt.where(health_water_models.HealthWater.date >= since)

    stmt = stmt.order_by(desc(health_water_models.HealthWater.date))

    if page_number is not None and num_records is not None:
        stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)

    return health_water_serializers.to_read_schemas(list(db.execute(stmt).scalars().all()))


def get_health_water_by_date_and_user_id(
    user_id: int, date: str, db: Session
) -> health_water_schema.HealthWaterRead | None:
    """Retrieve a user's water intake record for a date.

    Args:
        user_id: The record's owner.
        date: The record's date.
        db: Database session.

    Returns:
        The record, or ``None``.
    """
    stmt = select(health_water_models.HealthWater).where(
        health_water_models.HealthWater.date == func.date(date),
        health_water_models.HealthWater.user_id == user_id,
    )
    db_health_water = db.execute(stmt).scalar_one_or_none()

    return health_water_serializers.to_read_schema(db_health_water) if db_health_water else None


def create_health_water(
    user_id: int, health_water: health_water_schema.HealthWaterCreate, db: Session
) -> health_water_schema.HealthWaterRead:
    """Stage a new water intake record for a user.

    Args:
        user_id: The record's owner.
        health_water: The record to create.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the user already has a record for that date.
    """
    db_health_water = health_water_models.HealthWater(
        **health_water.model_dump(exclude_none=False),
        user_id=user_id,
    )

    try:
        db.add(db_health_water)
        db.flush()
        db.refresh(db_health_water)
    except IntegrityError as err:
        raise core_exceptions.ConflictError(
            f"Duplicate entry error. Check if there is already an entry created for {health_water.date}"
        ) from err

    return health_water_serializers.to_read_schema(db_health_water)


def edit_health_water(
    user_id: int, health_water: health_water_schema.HealthWaterUpdate, db: Session
) -> health_water_schema.HealthWaterRead:
    """Stage an update to a user's water intake record.

    Args:
        user_id: The record's owner.
        health_water: The record with its changes.
        db: Database session.

    Returns:
        The updated record.

    Raises:
        NotFoundError: If the user has no such record.
    """
    db_health_water = _get_model_by_id_and_user_id(health_water.id, user_id, db)

    for key, value in health_water.model_dump(exclude_unset=True).items():
        setattr(db_health_water, key, value)

    db.flush()
    db.refresh(db_health_water)

    return health_water_serializers.to_read_schema(db_health_water)


def add_health_water_amount(
    user_id: int, health_water_id: int, amount_ml: Decimal, source: str | None, db: Session
) -> health_water_schema.HealthWaterRead:
    """Stage an intake added to the total of a user's water intake record.

    The addition is one ``UPDATE``, so intakes added at the same moment, by this replica or
    another, are all counted.

    Args:
        user_id: The record's owner.
        health_water_id: The record to add to.
        amount_ml: Water consumed, in milliliters.
        source: Source of the intake.
        db: Database session.

    Returns:
        The updated record.

    Raises:
        NotFoundError: If the user has no such record.
    """
    db_health_water = _get_model_by_id_and_user_id(health_water_id, user_id, db)
    db.execute(
        update(health_water_models.HealthWater)
        .where(health_water_models.HealthWater.id == health_water_id)
        .values(amount_ml=health_water_models.HealthWater.amount_ml + amount_ml, source=source)
        .execution_options(synchronize_session=False)
    )
    db.refresh(db_health_water)

    return health_water_serializers.to_read_schema(db_health_water)


def delete_health_water(user_id: int, health_water_id: int, db: Session) -> None:
    """Stage the deletion of a user's water intake record.

    Args:
        user_id: The record's owner.
        health_water_id: The record to delete.
        db: Database session.

    Raises:
        NotFoundError: If the user has no such record.
    """
    db.delete(_get_model_by_id_and_user_id(health_water_id, user_id, db))
    db.flush()
