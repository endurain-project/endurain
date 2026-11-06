"""CRUD operations for health weight records."""

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import case, desc, func, select, update
from sqlalchemy.orm import Session

import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_weight.models as health_weight_models
import modules.health.health_weight.schema as health_weight_schema
import modules.health.record_crud as health_record_crud
import modules.health.schema as health_schema

SPEC = health_record_crud.RecordSpec(
    model=health_weight_models.HealthWeight,
    read_schema=health_weight_schema.HealthWeightRead,
    not_found="Health weight not found",
    etag_label="weight record",
)


def get_all_health_weight(db: Session) -> list[health_weight_schema.HealthWeightRead]:
    """Retrieve every weight record of every user (migration use only).

    Args:
        db: Database session.

    Returns:
        The records ordered by date descending.
    """
    stmt = select(health_weight_models.HealthWeight).order_by(desc(health_weight_models.HealthWeight.date))
    return health_computation.to_read_schemas(
        health_weight_schema.HealthWeightRead, list(db.execute(stmt).scalars().all())
    )


def get_health_weight_number_by_user_id(
    user_id: int, db: Session, since: date_type | None = None, until: date_type | None = None
) -> int:
    """Count a user's weight records.

    Args:
        user_id: The records' owner.
        db: Database session.
        since: Count only records on or after this date.
        until: Count only records on or before this date.

    Returns:
        The number of records.
    """
    return health_record_crud.count(SPEC, user_id, health_weight_models.HealthWeight.date, since, until, db)


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
    return health_computation.to_read_schemas(
        health_weight_schema.HealthWeightRead, list(db.execute(stmt).scalars().all())
    )


def get_health_weight_by_user_id(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    since: date_type | None = None,
    until: date_type | None = None,
) -> list[health_weight_schema.HealthWeightRead]:
    """Retrieve a user's weight records, optionally paginated and bounded.

    Args:
        user_id: The records' owner.
        db: Database session.
        page_number: 1-based page; paginates only together with ``num_records``.
        num_records: Records per page.
        since: Return only records on or after this date.
        until: Return only records on or before this date.

    Returns:
        The records ordered by date descending.
    """
    return health_record_crud.list_page(
        SPEC,
        user_id,
        health_weight_models.HealthWeight.date,
        health_weight_models.HealthWeight.date,
        since,
        until,
        page_number,
        num_records,
        db,
    )


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
    return health_record_crud.find_by_date(SPEC, user_id, date, db)


def get_latest_weight_by_user_id(
    user_id: int, on_or_before: date_type, db: Session
) -> health_weight_schema.HealthWeightRead | None:
    """Retrieve a user's most recent weight record dated no later than a day.

    A record dated after the day is not current, so it never shows as the latest weight.

    Args:
        user_id: The record's owner.
        on_or_before: The last day a record may be dated, the user's today.
        db: Database session.

    Returns:
        The latest record, or ``None``.
    """
    stmt = (
        select(health_weight_models.HealthWeight)
        .where(
            health_weight_models.HealthWeight.user_id == user_id,
            health_weight_models.HealthWeight.date <= on_or_before,
        )
        .order_by(desc(health_weight_models.HealthWeight.date))
        .limit(1)
    )
    db_health_weight = db.execute(stmt).scalar_one_or_none()

    return (
        health_computation.to_read_schema(health_weight_schema.HealthWeightRead, db_health_weight)
        if db_health_weight
        else None
    )


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
    return health_record_crud.create(
        SPEC, user_id, health_weight, db, conflict=health_record_crud.duplicate_date_message(health_weight.date)
    )


def edit_health_weight(
    user_id: int,
    health_weight_id: int,
    health_weight: health_weight_schema.HealthWeightUpdate,
    db: Session,
    *,
    if_match: str,
) -> health_weight_schema.HealthWeightRead:
    """Stage an update to a user's weight record.

    Args:
        user_id: The record's owner.
        health_weight_id: The record to change.
        health_weight: The fields to change.
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
        health_weight_id,
        user_id,
        health_weight,
        db,
        if_match=if_match,
        conflict=health_record_crud.DATE_TAKEN_MESSAGE,
    )


def recalculate_bmi_for_user(user_id: int, height_cm: float | None, db: Session) -> None:
    """Stage a BMI recalculation for a user's manually entered weight records in one statement.

    A single bulk UPDATE keeps the work to a constant number of round trips
    regardless of how many records exist. Records from a provider (``source`` set)
    keep the BMI the provider reported. A result outside ``0`` to ``MAX_BMI`` is
    stored as ``NULL``, as :func:`modules.health.health_weight.bmi.calculate_bmi` does.

    Args:
        user_id: The records' owner.
        height_cm: The user's height in centimeters, or ``None`` if unknown.
        db: Database session.
    """
    model = health_weight_models.HealthWeight
    if height_cm and height_cm > 0:
        # bmi = weight (kg) * 10000 / height (cm) ** 2; the squared height is bound unrounded
        # (a metre value would be rounded to the weight column's scale and could be zero).
        calculated = model.weight * 10000 / (Decimal(str(height_cm)) ** 2)
        new_bmi = case((calculated.between(0, health_weight_schema.MAX_BMI), calculated), else_=None)
    else:
        # Without a usable height, BMI cannot be derived, so clear it.
        new_bmi = None

    stmt = (
        update(model)
        .where(model.user_id == user_id, model.source.is_(None))
        .values(bmi=new_bmi, version=model.version + 1)
    )
    db.execute(stmt)
    db.flush()


def delete_health_weight(user_id: int, health_weight_id: int, db: Session, *, if_match: str) -> None:
    """Stage the deletion of a user's weight record.

    Args:
        user_id: The record's owner.
        health_weight_id: The record to delete.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    health_record_crud.delete(SPEC, health_weight_id, user_id, db, if_match=if_match)


def get_health_weight_chart(
    user_id: int, since: date_type, until: date_type | None, bucket: health_constants.ChartBucket, db: Session
) -> list[health_schema.HealthChartPoint]:
    """Average a user's weight per chart bucket.

    Args:
        user_id: The records' owner.
        since: First day of the charted window.
        until: Last day of the charted window, or ``None`` for no upper bound.
        bucket: The span each point aggregates.
        db: Database session.

    Returns:
        The buckets that hold a value, oldest first.
    """
    model = health_weight_models.HealthWeight
    day = health_computation.chart_bucket_expression(model.date, bucket, since)
    stmt = (
        select(day, func.avg(model.weight))
        .where(
            model.user_id == user_id,
            model.weight.is_not(None),
            *health_computation.date_bounds(model.date, since, until),
        )
        .group_by(day)
        .order_by(day)
    )
    return [health_schema.HealthChartPoint(date=d, value=float(value)) for d, value in db.execute(stmt).all()]
