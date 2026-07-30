from sqlalchemy.orm import Session

import modules.health.health_weight.crud as health_weight_crud
import modules.health.health_weight.schema as health_weight_schema
import modules.users.users.crud as users_crud


def calculate_bmi(
    health_weight: (health_weight_schema.HealthWeightCreate | health_weight_schema.HealthWeightUpdate),
    user_id: int,
    db: Session,
) -> health_weight_schema.HealthWeightCreate | health_weight_schema.HealthWeightUpdate:
    """
    Calculate the Body Mass Index (BMI) for a health weight record.

    Args:
        health_weight: Health weight record with weight value.
        user_id: Unique identifier of the user.
        db: Database session.

    Returns:
        Updated health weight record with calculated BMI.
    """
    # Get the user from the database
    user = users_crud.get_user_by_id(user_id, db)

    # Calculate BMI if user and required data exist
    calculated_bmi = None
    if user is not None and user.height is not None and health_weight.weight is not None:
        # Calculate the bmi: weight (kg) / (height (m))^2
        calculated_bmi = float(health_weight.weight) / ((user.height / 100) ** 2)

    # Return updated model with BMI
    return health_weight.model_copy(update={"bmi": calculated_bmi})


def calculate_bmi_all_user_entries(user_id: int, db: Session) -> None:
    """
    Recalculate and persist BMI for all of a user's weight entries.

    Fetches the user once and delegates to a single bulk update,
    avoiding a per-entry query and commit cycle.

    Args:
        user_id: User ID whose entries should be processed.
        db: Database session.

    Returns:
        None
    """
    # Fetch the user once to read the height used for every entry.
    user = users_crud.get_user_by_id(user_id, db)
    height_cm = float(user.height) if user is not None and user.height is not None else None

    # Recalculate BMI for every entry in a single bulk statement.
    health_weight_crud.recalculate_bmi_for_user(user_id, height_cm, db)
