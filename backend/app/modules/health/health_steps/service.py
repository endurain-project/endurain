"""Application logic for health steps records.

Owns the ownership check, the interval-to-date resolution and the transaction
boundary. What other modules may consume lives in
:mod:`modules.health.health_steps.integration_service`.
"""

from typing import Any

from sqlalchemy.orm import Session

import core.date_range as core_date_range
import core.logger as core_logger
import core.pagination as core_pagination
import modules.health.constants as health_constants
import modules.health.health_steps.crud as health_steps_crud
import modules.health.health_steps.schema as health_steps_schema
import modules.health.record_service as health_record_service
import modules.health.schema as health_schema
import modules.users.users.integration_service as users_integration
import modules.users.users_profile.contracts as users_profile_contracts

logger = core_logger.get_logger(__name__)


def list_health_steps(
    user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_NUM_RECORDS,
    interval: health_constants.Interval | None = None,
    date_range: core_date_range.DateRange = core_date_range.DateRange(),
) -> core_pagination.Page[health_steps_schema.HealthStepsRead]:
    """List one page of a user's steps records with their total.

    Args:
        user_id: The records' owner.
        db: Database session.
        page_number: 1-based page.
        num_records: Records per page.
        interval: Return only records within this interval, looking back from today; ignored when
            ``date_range`` is set.
        date_range: Return only records within these inclusive dates instead of the interval.

    Returns:
        The page of records; ``total`` counts every record within the window.
    """
    return health_record_service.list_page(
        user_id,
        interval,
        date_range,
        page_number,
        num_records,
        lambda since, until: health_steps_crud.get_health_steps_number_by_user_id(user_id, db, since, until),
        lambda since, until: health_steps_crud.get_health_steps_by_user_id(
            user_id, db, page_number, num_records, since, until
        ),
        db,
    )


def stage_edit_health_steps(
    user_id: int,
    health_steps_id: int,
    health_steps: health_steps_schema.HealthStepsUpdate,
    db: Session,
    *,
    if_match: str,
) -> health_steps_schema.HealthStepsRead:
    """Stage an update to a steps record.

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
        PreconditionFailedError: If the record changed since the client read it.
    """
    return health_steps_crud.edit_health_steps(user_id, health_steps_id, health_steps, db, if_match=if_match)


def stage_upsert_health_steps(
    user_id: int, health_steps: health_steps_schema.HealthStepsImport, db: Session
) -> health_steps_schema.HealthStepsRead:
    """Stage a steps record, or an update to the user's record for the same date.

    A writer that creates the date first, on this replica or another, is not an error: the
    record it created is updated instead.

    Args:
        user_id: The record's owner.
        health_steps: The record to store.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the date's record cannot be created or found.
    """
    return health_record_service.upsert_dated(
        user_id,
        health_steps,
        health_steps_schema.HealthStepsImportUpdate,
        lambda day: health_steps_crud.get_health_steps_by_date_and_user_id(user_id, day, db),
        lambda record: health_steps_crud.create_health_steps(user_id, record, db),
        lambda record_id, update: stage_edit_health_steps(user_id, record_id, update, db, if_match="*"),
        db,
    )


def create_health_steps(
    user_id: int, health_steps: health_steps_schema.HealthStepsCreate, db: Session
) -> health_steps_schema.HealthStepsRead:
    """Create a steps record for the user's day, and commit.

    Args:
        user_id: The record's owner.
        health_steps: The record to create; a missing date is the user's local today.
        db: Database session.

    Returns:
        The created record.

    Raises:
        ConflictError: If the user already has a record for that date.
        InvalidInputError: If the date is after the user's local today.
    """
    if health_steps.date is None:
        health_steps.date = users_integration.local_today(user_id, db)
    else:
        health_record_service.require_not_future(user_id, health_steps.date, db, what="A steps record")
    created = health_steps_crud.create_health_steps(user_id, health_steps, db)
    db.commit()
    logger.info("Stored a steps record", extra=core_logger.context(user_id=user_id))
    return created


def edit_health_steps(
    user_id: int,
    health_steps_id: int,
    health_steps: health_steps_schema.HealthStepsUpdate,
    db: Session,
    *,
    if_match: str,
) -> health_steps_schema.HealthStepsRead:
    """Update a steps record and commit.

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
        InvalidInputError: If the new date is after the user's local today.
        PreconditionFailedError: If the record changed since the client read it.
    """
    health_record_service.require_not_future(user_id, health_steps.date, db, what="A steps record")
    updated = health_record_service.commit_write(
        health_steps_crud.SPEC,
        health_steps_id,
        user_id,
        lambda: stage_edit_health_steps(user_id, health_steps_id, health_steps, db, if_match=if_match),
        db,
        log_message="Edited a steps record",
    )
    return updated


def get_health_steps(user_id: int, health_steps_id: int, db: Session) -> health_steps_schema.HealthStepsRead:
    """Return one of a user's steps records.

    Args:
        user_id: The record's owner.
        health_steps_id: The record to fetch.
        db: Database session.

    Returns:
        The record.

    Raises:
        NotFoundError: If the user has no such record.
    """
    return health_record_service.get_record(health_steps_crud.SPEC, health_steps_id, user_id, db)


def delete_health_steps(user_id: int, health_steps_id: int, db: Session, *, if_match: str) -> None:
    """Delete a steps record and commit.

    Args:
        user_id: The record's owner.
        health_steps_id: The record to delete.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: If the record changed since the client read it.
    """
    health_record_service.commit_write(
        health_steps_crud.SPEC,
        health_steps_id,
        user_id,
        lambda: health_steps_crud.delete_health_steps(user_id, health_steps_id, db, if_match=if_match),
        db,
        log_message="Deleted a steps record",
    )


def get_health_steps_chart(
    user_id: int,
    interval: health_constants.Interval,
    db: Session,
    *,
    date_range: core_date_range.DateRange = core_date_range.DateRange(),
) -> health_schema.HealthChartSeries:
    """Chart a user's steps over an interval.

    Args:
        user_id: The records' owner.
        interval: The window to chart, looking back from today; ignored when ``date_range`` is set.
        date_range: The inclusive dates to chart instead of the interval.
        db: Database session.

    Returns:
        The interval's buckets, one point per bucket that holds a value.
    """
    return health_record_service.chart(
        user_id,
        interval,
        date_range,
        lambda since, until, bucket: health_steps_crud.get_health_steps_chart(user_id, since, until, bucket, db),
        db,
    )


def restore_profile_records(
    records: list[dict[str, Any]], user_id: int, ids: users_profile_contracts.ProfileIdMaps, db: Session
) -> int:
    """Stage the steps records of a profile archive for a user.

    Args:
        records: The archived rows.
        user_id: The importing user.
        ids: The ids restored by earlier sections; the steps records read none.
        db: Database session.

    Returns:
        The number of records staged.
    """
    return health_record_service.restore_archived_records(
        records,
        health_steps_schema.HealthStepsImport,
        stage_upsert_health_steps,
        user_id,
        db,
        kind="health_steps",
    )
