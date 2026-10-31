"""Application logic for health sleep records.

Owns sleep scoring, the ownership check, the interval-to-date resolution and the
transaction boundary. What other modules may consume lives in
:mod:`modules.health.health_sleep.integration_service`.
"""

from sqlalchemy.orm import Session

import core.logger as core_logger
import core.pagination as core_pagination
import modules.health.constants as health_constants
import modules.health.health_sleep.crud as health_sleep_crud
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.health_sleep.sleep_scoring as health_sleep_sleep_scoring
import modules.health.record_service as health_record_service
import modules.health.schema as health_schema
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


def list_health_sleep(
    user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_NUM_RECORDS,
    interval: health_constants.Interval | None = None,
) -> core_pagination.Page[health_sleep_schema.HealthSleepRead]:
    """List one page of a user's sleep records with their total.

    Args:
        user_id: The records' owner.
        db: Database session.
        page_number: 1-based page.
        num_records: Records per page.
        interval: Return only records within this interval.

    Returns:
        The page of records; ``total`` counts every record within the interval.
    """
    return health_record_service.list_page(
        user_id,
        interval,
        page_number,
        num_records,
        lambda since: health_sleep_crud.get_health_sleep_number_by_user_id(user_id, db, since),
        lambda since: health_sleep_crud.get_health_sleep_by_user_id(user_id, db, page_number, num_records, since),
        db,
    )


def stage_edit_health_sleep(
    user_id: int,
    health_sleep_id: int,
    health_sleep: health_sleep_schema.HealthSleepUpdate,
    db: Session,
    *,
    if_match: str,
) -> health_sleep_schema.HealthSleepRead:
    """Stage an update to a sleep record.

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
        PreconditionFailedError: If the record changed since the client read it.
    """
    return health_sleep_crud.edit_health_sleep(user_id, health_sleep_id, health_sleep, db, if_match=if_match)


def stage_upsert_health_sleep(
    user_id: int, health_sleep: health_sleep_schema.HealthSleepCreate, db: Session
) -> health_sleep_schema.HealthSleepRead:
    """Stage a sleep record, or an update to the user's record for the same date.

    The record is stored as given: scoring is the caller's business.

    A writer that creates the date first, on this replica or another, is not an error: the
    record it created is updated instead.

    Args:
        user_id: The record's owner.
        health_sleep: The record to store.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the date's record cannot be created or found.
    """
    return health_record_service.upsert_dated(
        user_id,
        health_sleep,
        health_sleep_schema.HealthSleepUpdate,
        lambda day: health_sleep_crud.get_health_sleep_by_date_and_user_id(user_id, day, db),
        lambda record: health_sleep_crud.create_health_sleep(user_id, record, db),
        lambda record_id, update: stage_edit_health_sleep(user_id, record_id, update, db, if_match="*"),
        db,
    )


def create_health_sleep(
    user_id: int, health_sleep: health_sleep_schema.HealthSleepCreate, db: Session
) -> health_sleep_schema.HealthSleepRead:
    """Create a sleep record for the user's day, and commit.

    Args:
        user_id: The record's owner.
        health_sleep: The record to create; a missing date is the user's local today.
        db: Database session.

    Returns:
        The created record.

    Raises:
        ConflictError: If the user already has a record for that date.
    """
    if health_sleep.date is None:
        health_sleep.date = users_integration.local_today(user_id, db)
    health_sleep_sleep_scoring.calculate_and_set_sleep_scores(health_sleep)
    created = health_sleep_crud.create_health_sleep(user_id, health_sleep, db)
    db.commit()
    logger.info("Stored a sleep record", extra=core_logger.context(user_id=user_id))
    return created


def _score_edit(
    user_id: int, health_sleep_id: int, health_sleep: health_sleep_schema.HealthSleepUpdate, db: Session
) -> None:
    """Set the scores of an update from the record the update produces.

    The scores follow the stored record with the update's fields laid over it. An update that sends no
    scoring input keeps the stored scores, and scores the client sends never reach the record.

    Args:
        user_id: The record's owner.
        health_sleep_id: The record the update changes.
        health_sleep: The update; its score fields are set in place.
        db: Database session.

    Raises:
        NotFoundError: If the user has no such record.
    """
    stored = health_sleep_crud.get_health_sleep_by_id(user_id, health_sleep_id, db)
    health_sleep.model_fields_set.difference_update(health_sleep_sleep_scoring.SCORE_FIELDS)
    sent = health_sleep.model_dump(exclude_unset=True)
    if not health_sleep_sleep_scoring.SCORING_INPUT_FIELDS & sent.keys():
        return
    merged = stored.model_copy(update=sent)
    health_sleep_sleep_scoring.calculate_and_set_sleep_scores(merged)
    for field in health_sleep_sleep_scoring.SCORE_FIELDS:
        setattr(health_sleep, field, getattr(merged, field))


def edit_health_sleep(
    user_id: int,
    health_sleep_id: int,
    health_sleep: health_sleep_schema.HealthSleepUpdate,
    db: Session,
    *,
    if_match: str,
) -> health_sleep_schema.HealthSleepRead:
    """Score and update a sleep record, and commit.

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
        PreconditionFailedError: If the record changed since the client read it.
    """

    def stage() -> health_sleep_schema.HealthSleepRead:
        _score_edit(user_id, health_sleep_id, health_sleep, db)
        return stage_edit_health_sleep(user_id, health_sleep_id, health_sleep, db, if_match=if_match)

    updated = health_record_service.commit_write(
        health_sleep_crud.SPEC,
        health_sleep_id,
        user_id,
        stage,
        db,
        log_message="Edited a sleep record",
    )
    return updated


def delete_health_sleep(user_id: int, health_sleep_id: int, db: Session, *, if_match: str) -> None:
    """Delete a sleep record and commit.

    Args:
        user_id: The record's owner.
        health_sleep_id: The record to delete.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: If the record changed since the client read it.
    """
    health_record_service.commit_write(
        health_sleep_crud.SPEC,
        health_sleep_id,
        user_id,
        lambda: health_sleep_crud.delete_health_sleep(user_id, health_sleep_id, db, if_match=if_match),
        db,
        log_message="Deleted a sleep record",
    )


def get_health_sleep_chart(
    user_id: int, interval: health_constants.Interval, db: Session
) -> health_schema.HealthChartSeries:
    """Chart a user's total sleep seconds over an interval.

    Args:
        user_id: The records' owner.
        interval: The window to chart.
        db: Database session.

    Returns:
        The interval's buckets, one point per bucket that holds a value.
    """
    return health_record_service.chart(
        user_id,
        interval,
        lambda since, bucket: health_sleep_crud.get_health_sleep_chart(user_id, since, bucket, db),
        db,
    )


def get_health_sleep_resting_heart_rate_chart(
    user_id: int, interval: health_constants.Interval, db: Session
) -> health_schema.HealthChartSeries:
    """Chart a user's resting heart rate over an interval.

    Args:
        user_id: The records' owner.
        interval: The window to chart.
        db: Database session.

    Returns:
        The interval's buckets, one point per bucket that holds a value.
    """
    return health_record_service.chart(
        user_id,
        interval,
        lambda since, bucket: health_sleep_crud.get_health_sleep_resting_heart_rate_chart(user_id, since, bucket, db),
        db,
    )
