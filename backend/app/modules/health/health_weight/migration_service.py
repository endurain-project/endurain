"""The health weight operations exposed only to data migrations."""

from sqlalchemy.orm import Session

import modules.health.health_weight.crud as health_weight_crud
import modules.health.health_weight.schema as health_weight_schema
import modules.health.health_weight.service as health_weight_service


def get_all_health_weight(db: Session) -> list[health_weight_schema.HealthWeightRead]:
    """Return every weight record of every user.

    Args:
        db: Database session.

    Returns:
        The records, newest first.
    """
    return health_weight_crud.get_all_health_weight(db)


def edit_health_weight(
    user_id: int, health_weight_id: int, health_weight: health_weight_schema.HealthWeightUpdate, db: Session
) -> health_weight_schema.HealthWeightRead:
    """Edit a weight record, deriving its BMI, and commit it, as migrations did.

    Args:
        user_id: The record's owner.
        health_weight_id: The record to change.
        health_weight: The fields to change.
        db: Database session.

    Returns:
        The updated record.
    """
    return health_weight_service.edit_health_weight(user_id, health_weight_id, health_weight, db)
