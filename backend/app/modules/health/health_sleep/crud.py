"""CRUD operations for health sleep records."""

from datetime import date as date_type

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.etag as core_etag
import core.exceptions as core_exceptions
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_sleep.models as health_sleep_models
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.health_sleep.serializers as health_sleep_serializers
import modules.health.schema as health_schema


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


def health_sleep_exists(health_sleep_id: int, user_id: int, db: Session) -> bool:
    """Report whether a user has a sleep record.

    Args:
        health_sleep_id: The record to look for.
        user_id: The record's owner.
        db: Database session.

    Returns:
        True when the user has such a record.
    """
    stmt = select(
        select(health_sleep_models.HealthSleep.id)
        .where(
            health_sleep_models.HealthSleep.id == health_sleep_id, health_sleep_models.HealthSleep.user_id == user_id
        )
        .exists()
    )
    return bool(db.execute(stmt).scalar())


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
    user_id: int,
    health_sleep_id: int,
    health_sleep: health_sleep_schema.HealthSleepUpdate,
    db: Session,
    *,
    if_match: str,
) -> health_sleep_schema.HealthSleepRead:
    """Stage an update to a user's sleep record.

    Args:
        user_id: The record's owner.
        health_sleep_id: The record to change.
        health_sleep: The fields to change.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated record.

    Raises:
        NotFoundError: If the user has no such record.
        ConflictError: If the new date already has a record.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    db_health_sleep = _get_model_by_id_and_user_id(health_sleep_id, user_id, db)
    core_etag.require_if_match(if_match, db_health_sleep.version, "sleep record")

    for key, value in health_sleep.model_dump(exclude_unset=True, mode="json").items():
        setattr(db_health_sleep, key, value)

    try:
        db.flush()
    except IntegrityError as err:
        raise core_exceptions.ConflictError("Another record already exists for that date") from err
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


def _average_by_bucket(
    column, user_id: int, since: date_type, bucket: health_constants.ChartBucket, db: Session
) -> list[health_schema.HealthChartPoint]:
    """Average a sleep column per chart bucket.

    Args:
        column: The sleep column to average.
        user_id: The records' owner.
        since: First day of the charted window.
        bucket: The span each point aggregates.
        db: Database session.

    Returns:
        The buckets that hold a value, oldest first.
    """
    model = health_sleep_models.HealthSleep
    day = health_computation.chart_bucket_expression(model.date, bucket, since)
    stmt = (
        select(day, func.avg(column))
        .where(model.user_id == user_id, column.is_not(None), model.date >= since)
        .group_by(day)
        .order_by(day)
    )
    return [health_schema.HealthChartPoint(date=d, value=float(value)) for d, value in db.execute(stmt).all()]


def get_health_sleep_chart(
    user_id: int, since: date_type, bucket: health_constants.ChartBucket, db: Session
) -> list[health_schema.HealthChartPoint]:
    """Average a user's total sleep seconds per chart bucket.

    Args:
        user_id: The records' owner.
        since: First day of the charted window.
        bucket: The span each point aggregates.
        db: Database session.

    Returns:
        The buckets that hold a value, oldest first.
    """
    return _average_by_bucket(health_sleep_models.HealthSleep.total_sleep_seconds, user_id, since, bucket, db)


def get_health_sleep_resting_heart_rate_chart(
    user_id: int, since: date_type, bucket: health_constants.ChartBucket, db: Session
) -> list[health_schema.HealthChartPoint]:
    """Average a user's resting heart rate per chart bucket.

    Args:
        user_id: The records' owner.
        since: First day of the charted window.
        bucket: The span each point aggregates.
        db: Database session.

    Returns:
        The buckets that hold a value, oldest first.
    """
    return _average_by_bucket(health_sleep_models.HealthSleep.resting_heart_rate, user_id, since, bucket, db)
