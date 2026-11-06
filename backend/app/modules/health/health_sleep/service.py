"""Application logic for health sleep records.

Owns sleep scoring, the ownership check, the interval-to-date resolution and the
transaction boundary. What other modules may consume lives in
:mod:`modules.health.health_sleep.integration_service`.
"""

from typing import Any

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import core.pagination as core_pagination
import core.timezone as core_timezone
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_sleep.crud as health_sleep_crud
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.health_sleep.sleep_scoring as health_sleep_sleep_scoring
import modules.health.record_service as health_record_service
import modules.health.schema as health_schema
import modules.users.users.integration_service as users_integration
import modules.users.users_profile.contracts as users_profile_contracts

logger = core_logger.get_logger(__name__)

#: Minute rounding a provider applies to the stage durations and to the total.
_TOLERANCE_SECONDS = 60


def _require_consistent(sleep: health_sleep_schema.HealthSleepBase) -> None:
    """Refuse a sleep record whose stages, total or readings contradict each other.

    The total is the time asleep, as Garmin Connect reports it: deep, light and REM sleep, with awake time
    counted apart. So the sleeping stages cannot add up to more than the total, and the total cannot be
    longer than the span from falling asleep to waking. The GMT times bound the total, or the local times
    when there are no GMT times. The lowest reading of a pair cannot exceed its highest. Only manual writes are
    checked; a provider's record is stored as it is.

    Args:
        sleep: The record a manual write produces, whole.

    Raises:
        InvalidInputError: If the stages add up to more than the total, the total is longer than the span,
            or a minimum reading is above its maximum.
    """
    for low, high, name in (
        (sleep.min_heart_rate, sleep.max_heart_rate, "heart rate"),
        (sleep.lowest_spo2, sleep.highest_spo2, "SpO2"),
    ):
        if low is not None and high is not None and low > high:
            raise core_exceptions.InvalidInputError(f"The lowest {name} cannot be above the highest")
    total = sleep.total_sleep_seconds
    if total is None:
        return
    stages = (sleep.deep_sleep_seconds, sleep.light_sleep_seconds, sleep.rem_sleep_seconds)
    if sum(seconds or 0 for seconds in stages) > total + _TOLERANCE_SECONDS:
        raise core_exceptions.InvalidInputError(
            "The deep, light and REM sleep cannot add up to more than the total sleep"
        )
    start, end = (
        (sleep.sleep_start_time_gmt, sleep.sleep_end_time_gmt)
        if sleep.sleep_start_time_gmt is not None and sleep.sleep_end_time_gmt is not None
        else (sleep.sleep_start_time_local, sleep.sleep_end_time_local)
    )
    if (
        start is not None
        and end is not None
        and total
        > (core_timezone.to_utc_aware(end) - core_timezone.to_utc_aware(start)).total_seconds() + _TOLERANCE_SECONDS
    ):
        raise core_exceptions.InvalidInputError(
            "The total sleep cannot be longer than the time between the start and the end"
        )


def list_health_sleep(
    user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_NUM_RECORDS,
    interval: health_constants.Interval | None = None,
    date_range: health_computation.DateRange = health_computation.DateRange(),
) -> core_pagination.Page[health_sleep_schema.HealthSleepRead]:
    """List one page of a user's sleep records with their total.

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
        lambda since, until: health_sleep_crud.get_health_sleep_number_by_user_id(user_id, db, since, until),
        lambda since, until: health_sleep_crud.get_health_sleep_by_user_id(
            user_id, db, page_number, num_records, since, until
        ),
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
    user_id: int, health_sleep: health_sleep_schema.HealthSleepImport, db: Session
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
        health_sleep_schema.HealthSleepImportUpdate,
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
        InvalidInputError: If the stages, the total or the readings contradict each other.
    """
    if health_sleep.date is None:
        health_sleep.date = users_integration.local_today(user_id, db)
    _require_consistent(health_sleep)
    health_sleep_sleep_scoring.calculate_and_set_sleep_scores(health_sleep)
    created = health_sleep_crud.create_health_sleep(user_id, health_sleep, db)
    db.commit()
    logger.info("Stored a sleep record", extra=core_logger.context(user_id=user_id))
    return created


def _check_and_score_edit(
    user_id: int, health_sleep_id: int, health_sleep: health_sleep_schema.HealthSleepUpdate, db: Session
) -> None:
    """Refuse an update that makes the record contradict itself, and set the scores it produces.

    The update is checked as the stored record with its fields laid over it. The scores follow the stored record with the update's fields laid over it. An update that sends no
    scoring input keeps the stored scores, and scores the client sends never reach the record.

    Args:
        user_id: The record's owner.
        health_sleep_id: The record the update changes.
        health_sleep: The update; its score fields are set in place.
        db: Database session.

    Raises:
        NotFoundError: If the user has no such record.
        InvalidInputError: If the stages, the total or the readings contradict each other.
    """
    stored = health_sleep_crud.get_health_sleep_by_id(user_id, health_sleep_id, db)
    health_sleep.model_fields_set.difference_update(health_sleep_sleep_scoring.SCORE_FIELDS)
    sent = health_sleep.model_dump(exclude_unset=True)
    merged = stored.model_copy(update=sent)
    _require_consistent(merged)
    if not health_sleep_sleep_scoring.SCORING_INPUT_FIELDS & sent.keys():
        return
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
        InvalidInputError: If the stages, the total or the readings contradict each other.
        PreconditionFailedError: If the record changed since the client read it.
    """

    def stage() -> health_sleep_schema.HealthSleepRead:
        _check_and_score_edit(user_id, health_sleep_id, health_sleep, db)
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


def get_health_sleep(user_id: int, health_sleep_id: int, db: Session) -> health_sleep_schema.HealthSleepRead:
    """Return one of a user's sleep records.

    Args:
        user_id: The record's owner.
        health_sleep_id: The record to fetch.
        db: Database session.

    Returns:
        The record.

    Raises:
        NotFoundError: If the user has no such record.
    """
    return health_record_service.get_record(health_sleep_crud.SPEC, health_sleep_id, user_id, db)


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
    user_id: int,
    interval: health_constants.Interval,
    db: Session,
    *,
    date_range: health_computation.DateRange = health_computation.DateRange(),
) -> health_schema.HealthChartSeries:
    """Chart a user's total sleep seconds over an interval.

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
        lambda since, until, bucket: health_sleep_crud.get_health_sleep_chart(user_id, since, until, bucket, db),
        db,
    )


def get_health_sleep_resting_heart_rate_chart(
    user_id: int,
    interval: health_constants.Interval,
    db: Session,
    *,
    date_range: health_computation.DateRange = health_computation.DateRange(),
) -> health_schema.HealthChartSeries:
    """Chart a user's resting heart rate over an interval.

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
        lambda since, until, bucket: health_sleep_crud.get_health_sleep_resting_heart_rate_chart(
            user_id, since, until, bucket, db
        ),
        db,
    )


def restore_profile_records(
    records: list[dict[str, Any]], user_id: int, ids: users_profile_contracts.ProfileIdMaps, db: Session
) -> int:
    """Stage the sleep records of a profile archive for a user.

    Args:
        records: The archived rows.
        user_id: The importing user.
        ids: The ids restored by earlier sections; the sleep records read none.
        db: Database session.

    Returns:
        The number of records staged.
    """
    return health_record_service.restore_archived_records(
        records,
        health_sleep_schema.HealthSleepImport,
        stage_upsert_health_sleep,
        user_id,
        db,
        kind="health_sleep",
    )
