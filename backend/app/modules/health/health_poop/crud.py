"""CRUD operations for health poop (bowel movement) records."""

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_poop.models as health_poop_models
import modules.health.health_poop.schema as health_poop_schema
import modules.health.record_crud as health_record_crud
import modules.health.schema as health_schema

SPEC = health_record_crud.RecordSpec(
    model=health_poop_models.HealthPoop,
    read_schema=health_poop_schema.HealthPoopRead,
    not_found="Health poop not found",
    etag_label="bowel movement record",
)


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
    since_column = health_computation.local_date_expression(health_poop_models.HealthPoop.date_time, tz_name)
    return health_record_crud.count(SPEC, user_id, since_column, since, db)


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
    return health_record_crud.find_by_id(SPEC, health_poop_id, user_id, db)


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
    since_column = health_computation.local_date_expression(health_poop_models.HealthPoop.date_time, tz_name)
    return health_record_crud.list_page(
        SPEC, user_id, health_poop_models.HealthPoop.date_time, since_column, since, page_number, num_records, db
    )


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

    return health_computation.to_read_schemas(health_poop_schema.HealthPoopRead, list(db.execute(stmt).scalars().all()))


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
    return health_record_crud.create(
        SPEC, user_id, health_poop, db, conflict="Failed to create poop record. Database integrity error."
    )


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
    return health_record_crud.edit(SPEC, health_poop_id, user_id, health_poop, db, if_match=if_match)


def delete_health_poop(user_id: int, health_poop_id: int, db: Session, *, if_match: str) -> None:
    """Stage the deletion of a user's poop record.

    Args:
        user_id: The record's owner.
        health_poop_id: The record to delete.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    health_record_crud.delete(SPEC, health_poop_id, user_id, db, if_match=if_match)


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
