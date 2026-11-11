"""CRUD operations for health steps records."""

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import core.sync as core_sync
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_steps.models as health_steps_models
import modules.health.health_steps.schema as health_steps_schema
import modules.health.record_crud as health_record_crud
import modules.health.schema as health_schema

SPEC = health_record_crud.RecordSpec(
    model=health_steps_models.HealthSteps,
    read_schema=health_steps_schema.HealthStepsRead,
    not_found="Health steps not found",
    etag_label="steps record",
    sync_type="health_steps",
)


def get_health_steps_number_by_user_id(
    user_id: int, db: Session, since: date_type | None = None, until: date_type | None = None
) -> int:
    """Count a user's steps records.

    Args:
        user_id: The records' owner.
        db: Database session.
        since: Count only records on or after this date.
        until: Count only records on or before this date.

    Returns:
        The number of records.
    """
    return health_record_crud.count(SPEC, user_id, health_steps_models.HealthSteps.date, since, until, db)


def get_health_steps_by_user_id(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    since: date_type | None = None,
    until: date_type | None = None,
) -> list[health_steps_schema.HealthStepsRead]:
    """Retrieve a user's steps records, optionally paginated and bounded.

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
        health_steps_models.HealthSteps.date,
        health_steps_models.HealthSteps.date,
        since,
        until,
        page_number,
        num_records,
        db,
    )


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
    return health_record_crud.find_by_date(SPEC, user_id, date, db)


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
    return health_record_crud.create(
        SPEC, user_id, health_steps, db, conflict=health_record_crud.duplicate_date_message(health_steps.date)
    )


def edit_health_steps(
    user_id: int,
    health_steps_id: int,
    health_steps: health_steps_schema.HealthStepsUpdate,
    db: Session,
    *,
    if_match: str,
) -> health_steps_schema.HealthStepsRead:
    """Stage an update to a user's steps record.

    Args:
        user_id: The record's owner.
        health_steps_id: The record to change.
        health_steps: The fields to change.
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
        health_steps_id,
        user_id,
        health_steps,
        db,
        if_match=if_match,
        conflict=health_record_crud.DATE_TAKEN_MESSAGE,
    )


def delete_health_steps(user_id: int, health_steps_id: int, db: Session, *, if_match: str) -> None:
    """Stage the deletion of a user's steps record.

    Args:
        user_id: The record's owner.
        health_steps_id: The record to delete.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    health_record_crud.delete(SPEC, health_steps_id, user_id, db, if_match=if_match)


def get_health_steps_chart(
    user_id: int, since: date_type, until: date_type | None, bucket: health_constants.ChartBucket, db: Session
) -> list[health_schema.HealthChartPoint]:
    """Average a user's steps per chart bucket.

    Args:
        user_id: The records' owner.
        since: First day of the charted window.
        until: Last day of the charted window, or ``None`` for no upper bound.
        bucket: The span each point aggregates.
        db: Database session.

    Returns:
        The buckets that hold a value, oldest first.
    """
    model = health_steps_models.HealthSteps
    day = health_computation.chart_bucket_expression(model.date, bucket, since)
    stmt = (
        select(day, func.avg(model.steps))
        .where(
            model.user_id == user_id,
            model.steps.is_not(None),
            *health_computation.date_bounds(model.date, since, until),
        )
        .group_by(day)
        .order_by(day)
    )
    return [health_schema.HealthChartPoint(date=d, value=float(value)) for d, value in db.execute(stmt).all()]


def list_changed(
    user_id: int, after: core_sync.Position | None, until: datetime, limit: int, db: Session
) -> list[health_steps_schema.HealthStepsRead]:
    """Retrieve a user's records changed after a position, oldest change first.

    Args:
        user_id: The records' owner.
        after: Return records strictly after this ``(updated_at, id)``; ``None`` from the first.
        until: Return only records changed before this instant.
        limit: The most records to return.
        db: Database session.

    Returns:
        The records, in ``(updated_at, id)`` order.
    """
    model = health_steps_models.HealthSteps
    return health_record_crud.list_changed(
        model, model.user_id, model.id, SPEC.read_schema, user_id, after, until, limit, db
    )
