"""CRUD operations for health water intake records."""

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_water.models as health_water_models
import modules.health.health_water.schema as health_water_schema
import modules.health.record_crud as health_record_crud
import modules.health.schema as health_schema

SPEC = health_record_crud.RecordSpec(
    model=health_water_models.HealthWater,
    read_schema=health_water_schema.HealthWaterRead,
    not_found="Health water not found",
    etag_label="water intake record",
)


def get_health_water_number_by_user_id(user_id: int, db: Session, since: date_type | None = None) -> int:
    """Count a user's water intake records.

    Args:
        user_id: The records' owner.
        db: Database session.
        since: Count only records on or after this date.

    Returns:
        The number of records.
    """
    return health_record_crud.count(SPEC, user_id, health_water_models.HealthWater.date, since, db)


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
    return health_record_crud.list_page(
        SPEC,
        user_id,
        health_water_models.HealthWater.date,
        health_water_models.HealthWater.date,
        since,
        page_number,
        num_records,
        db,
    )


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
    return health_record_crud.find_by_date(SPEC, user_id, date, db)


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
    return health_record_crud.create(
        SPEC, user_id, health_water, db, conflict=health_record_crud.duplicate_date_message(health_water.date)
    )


def edit_health_water(
    user_id: int,
    health_water_id: int,
    health_water: health_water_schema.HealthWaterUpdate,
    db: Session,
    *,
    if_match: str,
) -> health_water_schema.HealthWaterRead:
    """Stage an update to a user's water intake record.

    Args:
        user_id: The record's owner.
        health_water_id: The record to change.
        health_water: The fields to change.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated record.

    Raises:
        NotFoundError: If the user has no such record.
        ConflictError: If the new date already has a record.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    return health_record_crud.edit(
        SPEC,
        health_water_id,
        user_id,
        health_water,
        db,
        if_match=if_match,
        conflict=health_record_crud.DATE_TAKEN_MESSAGE,
    )


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
    db_health_water = health_record_crud.get_owned(SPEC, health_water_id, user_id, db)
    db.execute(
        update(health_water_models.HealthWater)
        .where(health_water_models.HealthWater.id == health_water_id)
        .values(
            amount_ml=health_water_models.HealthWater.amount_ml + amount_ml,
            source=source,
            # A bulk UPDATE skips the ORM's version bump, and an intake is a change another client must see.
            version=health_water_models.HealthWater.version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    db.refresh(db_health_water)

    return health_computation.to_read_schema(health_water_schema.HealthWaterRead, db_health_water)


def delete_health_water(user_id: int, health_water_id: int, db: Session, *, if_match: str) -> None:
    """Stage the deletion of a user's water intake record.

    Args:
        user_id: The record's owner.
        health_water_id: The record to delete.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    health_record_crud.delete(SPEC, health_water_id, user_id, db, if_match=if_match)


def get_health_water_chart(
    user_id: int, since: date_type, bucket: health_constants.ChartBucket, db: Session
) -> list[health_schema.HealthChartPoint]:
    """Average a user's water intake per chart bucket.

    Args:
        user_id: The records' owner.
        since: First day of the charted window.
        bucket: The span each point aggregates.
        db: Database session.

    Returns:
        The buckets that hold a value, oldest first.
    """
    model = health_water_models.HealthWater
    day = health_computation.chart_bucket_expression(model.date, bucket, since)
    stmt = (
        select(day, func.avg(model.amount_ml))
        .where(model.user_id == user_id, model.amount_ml.is_not(None), model.date >= since)
        .group_by(day)
        .order_by(day)
    )
    return [health_schema.HealthChartPoint(date=d, value=float(value)) for d, value in db.execute(stmt).all()]
