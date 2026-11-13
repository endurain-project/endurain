"""Application logic for health weight records.

Owns the BMI rule (it needs the user's height; a manual write always derives it), the ownership check, the
interval-to-date resolution and the transaction boundary. What other modules may
consume lives in :mod:`modules.health.health_weight.integration_service`.
"""

import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

import core.date_range as core_date_range
import core.logger as core_logger
import core.pagination as core_pagination
import modules.health.constants as health_constants
import modules.health.health_weight.bmi as health_weight_bmi
import modules.health.health_weight.crud as health_weight_crud
import modules.health.health_weight.schema as health_weight_schema
import modules.health.record_service as health_record_service
import modules.health.schema as health_schema
import modules.users.users.integration_service as users_integration
import modules.users.users_profile.contracts as users_profile_contracts

logger = core_logger.get_logger(__name__)


def _user_height_cm(user_id: uuid.UUID, db: Session) -> float | None:
    """Return the user's height in centimeters, or ``None`` when unknown.

    Args:
        user_id: The user to look up.
        db: Database session.

    Returns:
        The height, or ``None``.
    """
    user = users_integration.get_user(user_id, db)
    return float(user.height) if user is not None and user.height is not None else None


def _with_bmi[RecordT: (health_weight_schema.HealthWeightCreate, health_weight_schema.HealthWeightUpdate)](
    health_weight: RecordT, user_id: uuid.UUID, db: Session
) -> RecordT:
    """Return the record with its BMI derived from the user's height.

    Args:
        health_weight: The record to complete.
        user_id: The record's owner.
        db: Database session.

    Returns:
        A copy carrying the calculated BMI.
    """
    bmi = health_weight_bmi.calculate_bmi(health_weight.weight_kg, _user_height_cm(user_id, db))
    return health_weight.model_copy(update={"bmi": bmi})


def list_health_weight(
    user_id: uuid.UUID,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_NUM_RECORDS,
    interval: health_constants.Interval | None = None,
    date_range: core_date_range.DateRange = core_date_range.DateRange(),
) -> core_pagination.Page[health_weight_schema.HealthWeightRead]:
    """List one page of a user's weight records with their total.

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
        lambda since, until: health_weight_crud.get_health_weight_number_by_user_id(user_id, db, since, until),
        lambda since, until: health_weight_crud.get_health_weight_by_user_id(
            user_id, db, page_number, num_records, since, until
        ),
        db,
    )


def stage_create_health_weight(
    user_id: uuid.UUID, health_weight: health_weight_schema.HealthWeightCreate, db: Session
) -> health_weight_schema.HealthWeightRead:
    """Stage a new manually entered weight record, deriving its BMI from the user's height.

    A BMI the client sent is ignored: it could contradict the weight and height the record is made of.

    Args:
        user_id: The record's owner.
        health_weight: The record to create.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the user already has a record for that date.
    """
    return health_weight_crud.create_health_weight(user_id, _with_bmi(health_weight, user_id, db), db)


def _stage_upsert_create(
    user_id: uuid.UUID, health_weight: health_weight_schema.HealthWeightImport, db: Session
) -> health_weight_schema.HealthWeightRead:
    """Stage a new weight record from a provider or an archive, which carry their own BMI.

    The BMI is derived only when the record has none.

    Args:
        user_id: The record's owner.
        health_weight: The record to create.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the user already has a record for that date.
    """
    record: health_weight_schema.HealthWeightCreate = health_weight
    if health_weight.bmi is None:
        record = _with_bmi(health_weight, user_id, db)
    return health_weight_crud.create_health_weight(user_id, record, db)


def stage_edit_health_weight(
    user_id: uuid.UUID,
    health_weight_id: uuid.UUID,
    health_weight: health_weight_schema.HealthWeightUpdate,
    db: Session,
    *,
    if_match: str,
) -> health_weight_schema.HealthWeightRead:
    """Stage an update to a manually entered weight record, deriving its BMI from the user's height.

    A BMI the client sent is ignored: it could contradict the weight and height the record is made of. An
    update without a weight leaves the stored BMI as it is.

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
        PreconditionFailedError: If the record changed since the client read it.
    """
    if health_weight.weight_kg is not None:
        health_weight = _with_bmi(health_weight, user_id, db)
    else:
        health_weight.model_fields_set.discard("bmi")
    return health_weight_crud.edit_health_weight(user_id, health_weight_id, health_weight, db, if_match=if_match)


def _stage_upsert_edit(
    user_id: uuid.UUID,
    health_weight_id: uuid.UUID,
    health_weight: health_weight_schema.HealthWeightImportUpdate,
    db: Session,
) -> health_weight_schema.HealthWeightRead:
    """Stage an update to a weight record from a provider or an archive, which carry their own BMI.

    The BMI is derived only when the update carries a weight and no BMI.

    Args:
        user_id: The record's owner.
        health_weight_id: The record to change.
        health_weight: The fields to change.
        db: Database session.

    Returns:
        The updated record.

    Raises:
        NotFoundError: If the user has no such record.
    """
    changes: health_weight_schema.HealthWeightUpdate = health_weight
    if health_weight.bmi is None and health_weight.weight_kg is not None:
        changes = _with_bmi(health_weight, user_id, db)
    return health_weight_crud.edit_health_weight(user_id, health_weight_id, changes, db, if_match="*")


def stage_upsert_health_weight(
    user_id: uuid.UUID, health_weight: health_weight_schema.HealthWeightImport, db: Session
) -> health_weight_schema.HealthWeightRead:
    """Stage a weight record, or an update to the user's record for the same date.

    The record comes from a provider or an archive, so its own BMI is kept.

    A writer that creates the date first, on this replica or another, is not an error: the
    record it created is updated instead.

    Args:
        user_id: The record's owner.
        health_weight: The record to store.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the date's record cannot be created or found.
    """
    return health_record_service.upsert_dated(
        user_id,
        health_weight,
        health_weight_schema.HealthWeightImportUpdate,
        lambda day: health_weight_crud.get_health_weight_by_date_and_user_id(user_id, day, db),
        lambda record: _stage_upsert_create(user_id, record, db),
        lambda record_id, update: _stage_upsert_edit(user_id, record_id, update, db),
        db,
    )


def create_health_weight(
    user_id: uuid.UUID, health_weight: health_weight_schema.HealthWeightCreate, db: Session
) -> health_weight_schema.HealthWeightRead:
    """Create a weight record for the user's day, and commit.

    Args:
        user_id: The record's owner.
        health_weight: The record to create; a missing date is the user's local today.
        db: Database session.

    Returns:
        The created record.

    Raises:
        ConflictError: If the user already has a record for that date.
        InvalidInputError: If the date is after the user's local today.
    """
    if health_weight.date is None:
        health_weight.date = users_integration.local_today(user_id, db)
    else:
        health_record_service.require_not_future(user_id, health_weight.date, db, what="A weight")
    created = stage_create_health_weight(user_id, health_weight, db)
    db.commit()
    logger.info("Stored a weight record", extra=core_logger.context(user_id=user_id))
    return created


def edit_health_weight(
    user_id: uuid.UUID,
    health_weight_id: uuid.UUID,
    health_weight: health_weight_schema.HealthWeightUpdate,
    db: Session,
    *,
    if_match: str,
) -> health_weight_schema.HealthWeightRead:
    """Update a weight record and commit.

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
        InvalidInputError: If the new date is after the user's local today.
        PreconditionFailedError: If the record changed since the client read it.
    """
    health_record_service.require_not_future(user_id, health_weight.date, db, what="A weight")
    updated = health_record_service.commit_write(
        health_weight_crud.SPEC,
        health_weight_id,
        user_id,
        lambda: stage_edit_health_weight(user_id, health_weight_id, health_weight, db, if_match=if_match),
        db,
        log_message="Edited a weight record",
    )
    return updated


def get_health_weight(
    user_id: uuid.UUID, health_weight_id: uuid.UUID, db: Session
) -> health_weight_schema.HealthWeightRead:
    """Return one of a user's weight records.

    Args:
        user_id: The record's owner.
        health_weight_id: The record to fetch.
        db: Database session.

    Returns:
        The record.

    Raises:
        NotFoundError: If the user has no such record.
    """
    return health_record_service.get_record(health_weight_crud.SPEC, health_weight_id, user_id, db)


def delete_health_weight(user_id: uuid.UUID, health_weight_id: uuid.UUID, db: Session, *, if_match: str) -> None:
    """Delete a weight record and commit.

    Args:
        user_id: The record's owner.
        health_weight_id: The record to delete.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: If the record changed since the client read it.
    """
    health_record_service.commit_write(
        health_weight_crud.SPEC,
        health_weight_id,
        user_id,
        lambda: health_weight_crud.delete_health_weight(user_id, health_weight_id, db, if_match=if_match),
        db,
        log_message="Deleted a weight record",
    )


def get_health_weight_chart(
    user_id: uuid.UUID,
    interval: health_constants.Interval,
    db: Session,
    *,
    date_range: core_date_range.DateRange = core_date_range.DateRange(),
) -> health_schema.HealthChartSeries:
    """Chart a user's weight over an interval.

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
        lambda since, until, bucket: health_weight_crud.get_health_weight_chart(user_id, since, until, bucket, db),
        db,
    )


def restore_profile_records(
    records: list[dict[str, Any]], user_id: uuid.UUID, ids: users_profile_contracts.ProfileIdMaps, db: Session
) -> int:
    """Stage the weight records of a profile archive for a user.

    Args:
        records: The archived rows.
        user_id: The importing user.
        ids: The ids restored by earlier sections; the weight records read none.
        db: Database session.

    Returns:
        The number of records staged.
    """
    staged = 0
    for health_weight in records:
        health_weight = users_profile_contracts.without_row_identity(health_weight)

        # Convert string numeric values to floats
        numeric_fields = [
            "weight_kg",
            "bmi",
            "body_fat_percent",
            "body_water_percent",
            "bone_mass_kg",
            "muscle_mass_kg",
            "visceral_fat",
        ]
        for field in numeric_fields:
            if field in health_weight and isinstance(health_weight[field], str):
                try:
                    health_weight[field] = float(health_weight[field])
                except (ValueError, TypeError):
                    health_weight[field] = None

        # Convert integer fields
        int_fields = ["physique_rating", "metabolic_age"]
        for field in int_fields:
            if field in health_weight and isinstance(health_weight[field], str):
                try:
                    health_weight[field] = int(health_weight[field])
                except (ValueError, TypeError):
                    health_weight[field] = None

        try:
            data = health_weight_schema.HealthWeightImport(**health_weight)
        except ValidationError:
            logger.warning("Skipped an invalid health weight record")
            continue
        stage_upsert_health_weight(user_id, data, db)
        staged += 1
    logger.debug("Imported health weight records", extra=core_logger.context(count=staged))
    return staged
