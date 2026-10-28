"""CRUD operations for health poop (bowel movement) records."""

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.etag as core_etag
import core.exceptions as core_exceptions
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_poop.models as health_poop_models
import modules.health.health_poop.schema as health_poop_schema
import modules.health.health_poop.serializers as health_poop_serializers
import modules.health.schema as health_schema


def _get_model_by_id_and_user_id(health_poop_id: int, user_id: int, db: Session) -> health_poop_models.HealthPoop:
    """Load a user's poop row by id.

    Args:
        health_poop_id: The record to load.
        user_id: The record's owner.
        db: Database session.

    Returns:
        The ORM row.

    Raises:
        NotFoundError: If the user has no such record.
    """
    stmt = select(health_poop_models.HealthPoop).where(
        health_poop_models.HealthPoop.id == health_poop_id,
        health_poop_models.HealthPoop.user_id == user_id,
    )
    db_health_poop = db.execute(stmt).scalar_one_or_none()

    if db_health_poop is None:
        raise core_exceptions.NotFoundError("Health poop not found")

    return db_health_poop


def health_poop_exists(health_poop_id: int, user_id: int, db: Session) -> bool:
    """Report whether a user has a bowel movement record.

    Args:
        health_poop_id: The record to look for.
        user_id: The record's owner.
        db: Database session.

    Returns:
        True when the user has such a record.
    """
    stmt = select(
        select(health_poop_models.HealthPoop.id)
        .where(health_poop_models.HealthPoop.id == health_poop_id, health_poop_models.HealthPoop.user_id == user_id)
        .exists()
    )
    return bool(db.execute(stmt).scalar())


def get_health_poop_number_by_user_id(
    user_id: int, db: Session, since: date_type | None = None, tz_name: str = "UTC"
) -> int:
    """Count a user's poop records.

    Args:
        user_id: The records' owner.
        db: Database session.
        since: Count only records on or after this day in ``tz_name``.
        tz_name: IANA timezone ``since`` is resolved in.

    Returns:
        The number of records.
    """
    stmt = (
        select(func.count())
        .select_from(health_poop_models.HealthPoop)
        .where(health_poop_models.HealthPoop.user_id == user_id)
    )
    if since is not None:
        stmt = stmt.where(
            health_computation.local_date_expression(health_poop_models.HealthPoop.date_time, tz_name) >= since
        )

    return db.execute(stmt).scalar_one()


def get_health_poop_by_id_and_user_id(
    health_poop_id: int, user_id: int, db: Session
) -> health_poop_schema.HealthPoopRead | None:
    """Retrieve a user's poop record by id.

    Args:
        health_poop_id: The record to fetch.
        user_id: The record's owner.
        db: Database session.

    Returns:
        The record, or ``None``.
    """
    stmt = select(health_poop_models.HealthPoop).where(
        health_poop_models.HealthPoop.id == health_poop_id,
        health_poop_models.HealthPoop.user_id == user_id,
    )
    db_health_poop = db.execute(stmt).scalar_one_or_none()

    return health_poop_serializers.to_read_schema(db_health_poop) if db_health_poop else None


def get_health_poop_by_user_id(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    since: date_type | None = None,
    tz_name: str = "UTC",
) -> list[health_poop_schema.HealthPoopRead]:
    """Retrieve a user's poop records, optionally paginated and bounded.

    Args:
        user_id: The records' owner.
        db: Database session.
        page_number: 1-based page; paginates only together with ``num_records``.
        num_records: Records per page.
        since: Return only records on or after this day in ``tz_name``.
        tz_name: IANA timezone ``since`` is resolved in.

    Returns:
        The records ordered by date and time descending.
    """
    stmt = select(health_poop_models.HealthPoop).where(health_poop_models.HealthPoop.user_id == user_id)

    if since is not None:
        stmt = stmt.where(
            health_computation.local_date_expression(health_poop_models.HealthPoop.date_time, tz_name) >= since
        )

    stmt = stmt.order_by(desc(health_poop_models.HealthPoop.date_time))

    if page_number is not None and num_records is not None:
        stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)

    return health_poop_serializers.to_read_schemas(list(db.execute(stmt).scalars().all()))


def get_health_poop_by_date_and_user_id(
    user_id: int, date: str, tz_name: str, db: Session
) -> list[health_poop_schema.HealthPoopRead]:
    """Retrieve a user's poop records for a calendar date in their own timezone.

    A day can hold several records, so this returns a list.

    Args:
        user_id: The records' owner.
        date: The calendar date.
        tz_name: IANA timezone the date is resolved in.
        db: Database session.

    Returns:
        The records of that date, newest first.
    """
    stmt = (
        select(health_poop_models.HealthPoop)
        .where(
            health_computation.local_date_expression(health_poop_models.HealthPoop.date_time, tz_name)
            == func.date(date),
            health_poop_models.HealthPoop.user_id == user_id,
        )
        .order_by(desc(health_poop_models.HealthPoop.date_time))
    )

    return health_poop_serializers.to_read_schemas(list(db.execute(stmt).scalars().all()))


def health_poop_exists_at(user_id: int, date_time: datetime, db: Session) -> bool:
    """Tell whether a user already has a poop record at an exact time.

    Args:
        user_id: The record's owner.
        date_time: The record's date and time.
        db: Database session.

    Returns:
        True when the user has a record at that time.
    """
    stmt = select(
        select(health_poop_models.HealthPoop.id)
        .where(
            health_poop_models.HealthPoop.user_id == user_id,
            health_poop_models.HealthPoop.date_time == date_time,
        )
        .exists()
    )
    return bool(db.execute(stmt).scalar())


def create_health_poop(
    user_id: int, health_poop: health_poop_schema.HealthPoopCreate, db: Session
) -> health_poop_schema.HealthPoopRead:
    """Stage a new poop record for a user.

    Args:
        user_id: The record's owner.
        health_poop: The record to create.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the insert violates a database constraint.
    """
    db_health_poop = health_poop_models.HealthPoop(
        **health_poop.model_dump(exclude_none=False),
        user_id=user_id,
    )

    try:
        db.add(db_health_poop)
        db.flush()
        db.refresh(db_health_poop)
    except IntegrityError as err:
        raise core_exceptions.ConflictError("Failed to create poop record. Database integrity error.") from err

    return health_poop_serializers.to_read_schema(db_health_poop)


def edit_health_poop(
    user_id: int, health_poop_id: int, health_poop: health_poop_schema.HealthPoopUpdate, db: Session, *, if_match: str
) -> health_poop_schema.HealthPoopRead:
    """Stage an update to a user's poop record.

    Args:
        user_id: The record's owner.
        health_poop_id: The record to change.
        health_poop: The fields to change.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated record.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    db_health_poop = _get_model_by_id_and_user_id(health_poop_id, user_id, db)
    core_etag.require_if_match(if_match, db_health_poop.version, "bowel movement record")

    for key, value in health_poop.model_dump(exclude_unset=True).items():
        setattr(db_health_poop, key, value)

    db.flush()
    db.refresh(db_health_poop)

    return health_poop_serializers.to_read_schema(db_health_poop)


def delete_health_poop(user_id: int, health_poop_id: int, db: Session) -> None:
    """Stage the deletion of a user's poop record.

    Args:
        user_id: The record's owner.
        health_poop_id: The record to delete.
        db: Database session.

    Raises:
        NotFoundError: If the user has no such record.
    """
    db.delete(_get_model_by_id_and_user_id(health_poop_id, user_id, db))
    db.flush()


def get_health_poop_chart(
    user_id: int, since: date_type, bucket: health_constants.ChartBucket, tz_name: str, db: Session
) -> list[health_schema.HealthChartPoint]:
    """Count a user's bowel movements per chart bucket, each filed under the day it happened in the user's zone.

    Args:
        user_id: The records' owner.
        since: First day of the charted window.
        bucket: The span each point aggregates.
        tz_name: IANA timezone the days are resolved in.
        db: Database session.

    Returns:
        The buckets that hold a movement, oldest first; each value is the movement count.
    """
    model = health_poop_models.HealthPoop
    local_day = health_computation.local_date_expression(model.date_time, tz_name)
    day = health_computation.chart_bucket_expression(local_day, bucket, since)
    stmt = select(day, func.count()).where(model.user_id == user_id, local_day >= since).group_by(day).order_by(day)
    return [health_schema.HealthChartPoint(date=d, value=float(count)) for d, count in db.execute(stmt).all()]


def get_health_poop_first_day(user_id: int, tz_name: str, db: Session) -> date_type | None:
    """Return the day of a user's first bowel movement in their own timezone.

    Args:
        user_id: The records' owner.
        tz_name: IANA timezone the day is resolved in.
        db: Database session.

    Returns:
        The day, or ``None`` when the user has no movements.
    """
    model = health_poop_models.HealthPoop
    stmt = select(func.min(health_computation.local_date_expression(model.date_time, tz_name))).where(
        model.user_id == user_id
    )
    return db.execute(stmt).scalar_one()
