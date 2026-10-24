"""CRUD operations for health sleep records."""

from datetime import date as date_type

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.health.health_sleep.models as health_sleep_models
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.health_sleep.serializers as health_sleep_serializers


def _get_model_by_id_and_user_id(health_sleep_id: int, user_id: int, db: Session) -> health_sleep_models.HealthSleep:
    """Load a user's sleep row by id.

    Args:
        health_sleep_id: The record to load.
        user_id: The record's owner.
        db: Database session.

    Returns:
        The ORM row.

    Raises:
        NotFoundError: If the user has no such record.
    """
    stmt = select(health_sleep_models.HealthSleep).where(
        health_sleep_models.HealthSleep.id == health_sleep_id,
        health_sleep_models.HealthSleep.user_id == user_id,
    )
    db_health_sleep = db.execute(stmt).scalar_one_or_none()

    if db_health_sleep is None:
        raise core_exceptions.NotFoundError("Health sleep not found")

    return db_health_sleep


def get_health_sleep_number_by_user_id(user_id: int, db: Session, since: date_type | None = None) -> int:
    """Count a user's sleep records.

    Args:
        user_id: The records' owner.
        db: Database session.
        since: Count only records on or after this date.

    Returns:
        The number of records.
    """
    stmt = (
        select(func.count())
        .select_from(health_sleep_models.HealthSleep)
        .where(health_sleep_models.HealthSleep.user_id == user_id)
    )
    if since is not None:
        stmt = stmt.where(health_sleep_models.HealthSleep.date >= since)

    return db.execute(stmt).scalar_one()


def get_health_sleep_by_user_id(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    since: date_type | None = None,
) -> list[health_sleep_schema.HealthSleepRead]:
    """Retrieve a user's sleep records, optionally paginated and bounded.

    Args:
        user_id: The records' owner.
        db: Database session.
        page_number: 1-based page; paginates only together with ``num_records``.
        num_records: Records per page.
        since: Return only records on or after this date.

    Returns:
        The records ordered by date descending.
    """
    stmt = select(health_sleep_models.HealthSleep).where(health_sleep_models.HealthSleep.user_id == user_id)

    if since is not None:
        stmt = stmt.where(health_sleep_models.HealthSleep.date >= since)

    stmt = stmt.order_by(desc(health_sleep_models.HealthSleep.date))

    if page_number is not None and num_records is not None:
        stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)

    return health_sleep_serializers.to_read_schemas(list(db.execute(stmt).scalars().all()))


def get_health_sleep_by_date_and_user_id(
    user_id: int, date: str, db: Session
) -> health_sleep_schema.HealthSleepRead | None:
    """Retrieve a user's sleep record for a date.

    Args:
        user_id: The record's owner.
        date: The record's date.
        db: Database session.

    Returns:
        The record, or ``None``.
    """
    stmt = select(health_sleep_models.HealthSleep).where(
        health_sleep_models.HealthSleep.date == func.date(date),
        health_sleep_models.HealthSleep.user_id == user_id,
    )
    db_health_sleep = db.execute(stmt).scalar_one_or_none()

    return health_sleep_serializers.to_read_schema(db_health_sleep) if db_health_sleep else None


def create_health_sleep(
    user_id: int, health_sleep: health_sleep_schema.HealthSleepCreate, db: Session
) -> health_sleep_schema.HealthSleepRead:
    """Stage a new sleep record for a user.

    Args:
        user_id: The record's owner.
        health_sleep: The record to create.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the user already has a record for that date.
    """
    db_health_sleep = health_sleep_models.HealthSleep(
        **health_sleep.model_dump(exclude_none=False, mode="json"),
        user_id=user_id,
    )

    try:
        db.add(db_health_sleep)
        db.flush()
        db.refresh(db_health_sleep)
    except IntegrityError as err:
        raise core_exceptions.ConflictError(
            f"Duplicate entry error. Check if there is already an entry created for {health_sleep.date}"
        ) from err

    return health_sleep_serializers.to_read_schema(db_health_sleep)


def edit_health_sleep(
    user_id: int, health_sleep: health_sleep_schema.HealthSleepUpdate, db: Session
) -> health_sleep_schema.HealthSleepRead:
    """Stage an update to a user's sleep record.

    Args:
        user_id: The record's owner.
        health_sleep: The record with its changes.
        db: Database session.

    Returns:
        The updated record.

    Raises:
        NotFoundError: If the user has no such record.
    """
    db_health_sleep = _get_model_by_id_and_user_id(health_sleep.id, user_id, db)

    for key, value in health_sleep.model_dump(exclude_unset=True, mode="json").items():
        setattr(db_health_sleep, key, value)

    db.flush()
    db.refresh(db_health_sleep)

    return health_sleep_serializers.to_read_schema(db_health_sleep)


def delete_health_sleep(user_id: int, health_sleep_id: int, db: Session) -> None:
    """Stage the deletion of a user's sleep record.

    Args:
        user_id: The record's owner.
        health_sleep_id: The record to delete.
        db: Database session.

    Raises:
        NotFoundError: If the user has no such record.
    """
    db.delete(_get_model_by_id_and_user_id(health_sleep_id, user_id, db))
    db.flush()
