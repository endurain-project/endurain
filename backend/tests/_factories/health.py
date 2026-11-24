"""Health records as the application stores them, for tests on the real database."""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

import modules.health.health_fasting.crud as health_fasting_crud
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.health_poop.crud as health_poop_crud
import modules.health.health_poop.schema as health_poop_schema
import modules.health.health_sleep.crud as health_sleep_crud
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.health_steps.crud as health_steps_crud
import modules.health.health_steps.schema as health_steps_schema
import modules.health.health_water.crud as health_water_crud
import modules.health.health_water.schema as health_water_schema
import modules.health.health_weight.crud as health_weight_crud
import modules.health.health_weight.schema as health_weight_schema

#: The day of a weight made without one.
DEFAULT_WEIGHT_DATE = date(2025, 1, 1)


def make_health_weight(db: Session, user_id: uuid.UUID, **overrides: object) -> health_weight_schema.HealthWeightRead:
    """Stage a weight record through the module's create function (flushed, not committed).

    A user has one record per day, so a test that stages several for one user gives each its own ``date``. The BMI is
    stored as given: it is derived only by the service, which the factory bypasses.

    Args:
        db: Database session.
        user_id: The record's owner.
        **overrides: Field values of :class:`~modules.health.health_weight.schema.HealthWeightImport` (``date``,
            ``weight_kg``, ``bmi``, ``source`` and the body-composition fields), which replace the defaults of a
            75 kg weight on :data:`DEFAULT_WEIGHT_DATE`.

    Returns:
        The staged record.
    """
    values: dict[str, object] = {"date": DEFAULT_WEIGHT_DATE, "weight_kg": 75.0}
    values.update(overrides)
    record = health_weight_schema.HealthWeightImport.model_validate(values)
    return health_weight_crud.create_health_weight(user_id, record, db)


def make_health_steps(db: Session, user_id: uuid.UUID, **overrides: object) -> health_steps_schema.HealthStepsRead:
    """Stage a steps record through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        user_id: The record's owner.
        **overrides: Field values of :class:`~modules.health.health_steps.schema.HealthStepsImport`, which replace
            the defaults of 5000 steps on :data:`DEFAULT_WEIGHT_DATE`.

    Returns:
        The staged record.
    """
    values: dict[str, object] = {"date": DEFAULT_WEIGHT_DATE, "steps": 5000}
    values.update(overrides)
    return health_steps_crud.create_health_steps(
        user_id, health_steps_schema.HealthStepsImport.model_validate(values), db
    )


def make_health_water(db: Session, user_id: uuid.UUID, **overrides: object) -> health_water_schema.HealthWaterRead:
    """Stage a water intake record through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        user_id: The record's owner.
        **overrides: Field values of :class:`~modules.health.health_water.schema.HealthWaterImport`, which replace
            the defaults of 500 ml on :data:`DEFAULT_WEIGHT_DATE`.

    Returns:
        The staged record.
    """
    values: dict[str, object] = {"date": DEFAULT_WEIGHT_DATE, "amount_ml": 500}
    values.update(overrides)
    return health_water_crud.create_health_water(
        user_id, health_water_schema.HealthWaterImport.model_validate(values), db
    )


def make_health_sleep(db: Session, user_id: uuid.UUID, **overrides: object) -> health_sleep_schema.HealthSleepRead:
    """Stage a sleep record through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        user_id: The record's owner.
        **overrides: Field values of :class:`~modules.health.health_sleep.schema.HealthSleepImport`, which replace
            the defaults of 7 hours of sleep on :data:`DEFAULT_WEIGHT_DATE`.

    Returns:
        The staged record.
    """
    values: dict[str, object] = {"date": DEFAULT_WEIGHT_DATE, "total_sleep_seconds": 25200}
    values.update(overrides)
    return health_sleep_crud.create_health_sleep(
        user_id, health_sleep_schema.HealthSleepImport.model_validate(values), db
    )


def make_health_poop(db: Session, user_id: uuid.UUID, **overrides: object) -> health_poop_schema.HealthPoopRead:
    """Stage a bowel movement record through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        user_id: The record's owner.
        **overrides: Field values of :class:`~modules.health.health_poop.schema.HealthPoopImport`, which replace the
            defaults of a record at midday UTC on :data:`DEFAULT_WEIGHT_DATE`.

    Returns:
        The staged record.
    """
    values: dict[str, object] = {"date_time": datetime(2025, 1, 1, 12, 0, tzinfo=UTC), "notes": "note"}
    values.update(overrides)
    return health_poop_crud.create_health_poop(user_id, health_poop_schema.HealthPoopImport.model_validate(values), db)


def make_health_fasting(
    db: Session, user_id: uuid.UUID, **overrides: object
) -> health_fasting_schema.HealthFastingRead:
    """Stage an ongoing fast through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        user_id: The record's owner.
        **overrides: Field values of :class:`~modules.health.health_fasting.schema.HealthFastingImport`, which
            replace the defaults of a fast that started at midday UTC on :data:`DEFAULT_WEIGHT_DATE` and has not ended.

    Returns:
        The staged record.
    """
    values: dict[str, object] = {"fast_start_time": datetime(2025, 1, 1, 12, 0, tzinfo=UTC)}
    values.update(overrides)
    return health_fasting_crud.create_health_fasting(
        user_id, health_fasting_schema.HealthFastingImport.model_validate(values), db, actual_duration_seconds=None
    )


def make_ended_health_fasting(
    db: Session,
    user_id: uuid.UUID,
    fast_start_time: datetime,
    fast_end_time: datetime,
    *,
    status: str = "completed",
    **overrides: object,
) -> health_fasting_schema.HealthFastingRead:
    """Stage a fast that ended, with the duration the service derives from its times (flushed, not committed).

    Args:
        db: Database session.
        user_id: The record's owner.
        fast_start_time: When the fast started.
        fast_end_time: When the fast ended.
        status: The fast's final status.
        **overrides: Further field values of :class:`~modules.health.health_fasting.schema.HealthFastingImport`.

    Returns:
        The staged record.
    """
    values: dict[str, object] = {
        "fast_start_time": fast_start_time,
        "fast_end_time": fast_end_time,
        "status": status,
        **overrides,
    }
    return health_fasting_crud.create_health_fasting(
        user_id,
        health_fasting_schema.HealthFastingImport.model_validate(values),
        db,
        actual_duration_seconds=int((fast_end_time - fast_start_time).total_seconds()),
    )
