"""CRUD operations for health steps records."""

from datetime import date as date_type

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.health.health_steps.models as health_steps_models
import modules.health.health_steps.schema as health_steps_schema
import modules.health.health_steps.serializers as health_steps_serializers


def _get_model_by_id_and_user_id(health_steps_id: int, user_id: int, db: Session) -> health_steps_models.HealthSteps:
    """Load a user's steps row by id.

    Args:
        health_steps_id: The record to load.
        user_id: The record's owner.
        db: Database session.

    Returns:
        The ORM row.

    Raises:
        NotFoundError: If the user has no such record.
    """
    stmt = select(health_steps_models.HealthSteps).where(
        health_steps_models.HealthSteps.id == health_steps_id,
        health_steps_models.HealthSteps.user_id == user_id,
    )
    db_health_steps = db.execute(stmt).scalar_one_or_none()

    if db_health_steps is None:
        raise core_exceptions.NotFoundError("Health steps not found")

    return db_health_steps


def get_health_steps_number_by_user_id(user_id: int, db: Session, since: date_type | None = None) -> int:
    """Count a user's steps records.

    Args:
        user_id: The records' owner.
        db: Database session.
        since: Count only records on or after this date.

    Returns:
        The number of records.
    """
    stmt = (
        select(func.count())
        .select_from(health_steps_models.HealthSteps)
        .where(health_steps_models.HealthSteps.user_id == user_id)
    )
    if since is not None:
        stmt = stmt.where(health_steps_models.HealthSteps.date >= since)

    return db.execute(stmt).scalar_one()


def get_health_steps_by_user_id(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    since: date_type | None = None,
) -> list[health_steps_schema.HealthStepsRead]:
    """Retrieve a user's steps records, optionally paginated and bounded.

    Args:
        user_id: The records' owner.
        db: Database session.
        page_number: 1-based page; paginates only together with ``num_records``.
        num_records: Records per page.
        since: Return only records on or after this date.

    Returns:
        The records ordered by date descending.
    """
    stmt = select(health_steps_models.HealthSteps).where(health_steps_models.HealthSteps.user_id == user_id)

    if since is not None:
        stmt = stmt.where(health_steps_models.HealthSteps.date >= since)

    stmt = stmt.order_by(desc(health_steps_models.HealthSteps.date))

    if page_number is not None and num_records is not None:
        stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)

    return health_steps_serializers.to_read_schemas(list(db.execute(stmt).scalars().all()))


def get_health_steps_by_date_and_user_id(
    user_id: int, date: str, db: Session
) -> health_steps_schema.HealthStepsRead | None:
    """Retrieve a user's steps record for a date.

    Args:
        user_id: The record's owner.
        date: The record's date.
        db: Database session.

    Returns:
        The record, or ``None``.
    """
    stmt = select(health_steps_models.HealthSteps).where(
        health_steps_models.HealthSteps.date == func.date(date),
        health_steps_models.HealthSteps.user_id == user_id,
    )
    db_health_steps = db.execute(stmt).scalar_one_or_none()

    return health_steps_serializers.to_read_schema(db_health_steps) if db_health_steps else None


def create_health_steps(
    user_id: int, health_steps: health_steps_schema.HealthStepsCreate, db: Session
) -> health_steps_schema.HealthStepsRead:
    """Stage a new steps record for a user.

    Args:
        user_id: The record's owner.
        health_steps: The record to create.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the user already has a record for that date.
    """
    db_health_steps = health_steps_models.HealthSteps(
        **health_steps.model_dump(exclude_none=False),
        user_id=user_id,
    )

    try:
        db.add(db_health_steps)
        db.flush()
        db.refresh(db_health_steps)
    except IntegrityError as err:
        raise core_exceptions.ConflictError(
            f"Duplicate entry error. Check if there is already a entry created for {health_steps.date}"
        ) from err

    return health_steps_serializers.to_read_schema(db_health_steps)


def edit_health_steps(
    user_id: int, health_steps: health_steps_schema.HealthStepsUpdate, db: Session
) -> health_steps_schema.HealthStepsRead:
    """Stage an update to a user's steps record.

    Args:
        user_id: The record's owner.
        health_steps: The record with its changes.
        db: Database session.

    Returns:
        The updated record.

    Raises:
        NotFoundError: If the user has no such record.
    """
    db_health_steps = _get_model_by_id_and_user_id(health_steps.id, user_id, db)

    for key, value in health_steps.model_dump(exclude_unset=True).items():
        setattr(db_health_steps, key, value)

    db.flush()
    db.refresh(db_health_steps)

    return health_steps_serializers.to_read_schema(db_health_steps)


def delete_health_steps(user_id: int, health_steps_id: int, db: Session) -> None:
    """Stage the deletion of a user's steps record.

    Args:
        user_id: The record's owner.
        health_steps_id: The record to delete.
        db: Database session.

    Raises:
        NotFoundError: If the user has no such record.
    """
    db.delete(_get_model_by_id_and_user_id(health_steps_id, user_id, db))
    db.flush()
