"""Health records as the application stores them, for tests on the real database."""

import uuid
from datetime import date

from sqlalchemy.orm import Session

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
