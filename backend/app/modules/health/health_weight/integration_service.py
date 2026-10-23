"""The operations other modules may call on health weight records."""

from sqlalchemy.orm import Session

import modules.health.health_weight.crud as health_weight_crud
import modules.health.health_weight.schema as health_weight_schema


def get_health_weight_by_date(user_id: int, date: str, db: Session) -> health_weight_schema.HealthWeightRead | None:
    """Return a user's weight record for a date, or ``None``.

    Args:
        user_id: The record's owner.
        date: The record's date.
        db: Database session.

    Returns:
        The record, or ``None``.
    """
    return health_weight_crud.get_health_weight_by_date_and_user_id(user_id, date, db)


def create_health_weight(
    user_id: int, health_weight: health_weight_schema.HealthWeightCreate, db: Session
) -> health_weight_schema.HealthWeightRead:
    """Create a weight record for a user.

    Args:
        user_id: The record's owner.
        health_weight: The record to create.
        db: Database session.

    Returns:
        The created record.
    """
    return health_weight_crud.create_health_weight(user_id, health_weight, db)


def edit_health_weight(
    user_id: int, health_weight: health_weight_schema.HealthWeightUpdate, db: Session
) -> health_weight_schema.HealthWeightRead:
    """Edit a user's weight record.

    Args:
        user_id: The record's owner.
        health_weight: The record with its changes.
        db: Database session.

    Returns:
        The edited record.
    """
    return health_weight_crud.edit_health_weight(user_id, health_weight, db)
