from typing import cast

from sqlalchemy.orm import Session

import users.users.crud as users_crud

import health.health_weight.schema as health_weight_schema
import health.health_weight.crud as health_weight_crud


def calculate_bmi(
    health_weight: (
        health_weight_schema.HealthWeightCreate
        | health_weight_schema.HealthWeightUpdate
    ),
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
    if (
        user is not None
        and user.height is not None
        and health_weight.weight is not None
    ):
        # Calculate the bmi: weight (kg) / (height (m))^2
        calculated_bmi = float(health_weight.weight) / ((user.height / 100) ** 2)

    # Return updated model with BMI
    return health_weight.model_copy(update={"bmi": calculated_bmi})


def calculate_bmi_all_user_entries(user_id: int, db: Session) -> None:
    """
    Calculate and update BMI for all health weight entries.

    Args:
        user_id: User ID whose entries should be processed.
        db: Database session.

    Returns:
        None
    """
    # Get all the health data entries for the user
    health_weight_entries = health_weight_crud.get_all_health_weight_by_user_id(
        user_id, db
    )

    # Check if health data entries exist
    if health_weight_entries:
        # Loop through and calculate BMI for each entry
        for health_weight in health_weight_entries:
            # Convert to update schema with the existing ID
            aux_health_weight = health_weight_schema.HealthWeightUpdate.model_validate(
                health_weight
            )
            updated_weight = cast(
                health_weight_schema.HealthWeightUpdate,
                calculate_bmi(aux_health_weight, user_id, db),
            )
            health_weight_crud.edit_health_weight(user_id, updated_weight, db)
