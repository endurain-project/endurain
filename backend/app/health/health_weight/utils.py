from sqlalchemy.orm import Session

import users.user.crud as users_crud

import health.health_weight.schema as health_weight_schema
import health.health_weight.crud as health_weight_crud


def calculate_bmi(
    health_weight: health_weight_schema.HealthWeight,
    user_id: int,
    db: Session,
) -> health_weight_schema.HealthWeight:
    """
    Calculate the Body Mass Index (BMI) for a health weight record.

    This function computes the BMI using the formula: weight (kg) / (height (m))^2.
    The height is retrieved from the user's profile and converted from centimeters to meters.
    If the user doesn't exist, or if height or weight data is missing, BMI is set to None.

    Args:
        health_weight (health_weight_schema.HealthWeight): The health weight record containing
            the weight value and where the calculated BMI will be stored.
        user_id (int): The unique identifier of the user.
        db (Session): The database session object for querying user data.

    Returns:
        health_weight_schema.HealthWeight: The updated health weight record with the calculated
            BMI value (or None if calculation is not possible).
    """
    # Get the user from the database
    user = users_crud.get_user_by_id(user_id, db)

    # Check if user is not None and user height is not None and health_weight weight is not None
    if (
        user is not None
        and user.height is not None
        and health_weight.weight is not None
    ):
        # Calculate the bmi
        health_weight.bmi = float(health_weight.weight) / ((user.height / 100) ** 2)
    else:
        # Set bmi to None if user doesn't exist or height is missing
        health_weight.bmi = None

    # return the health weight
    return health_weight


def calculate_bmi_all_user_entries(user_id: int, db: Session) -> None:
    """
    Calculate and update BMI for all health weight entries of a specific user.

    This function retrieves all health weight entries for a given user, calculates
    the BMI for each entry using the calculate_bmi function, and updates the
    database with the calculated BMI values.

    Args:
        user_id (int): The unique identifier of the user whose health weight
            entries should be processed.
        db (Session): The database session object used for database operations.

    Returns:
        None
    """
    # Get all the health data entries for the user
    health_weight_entries = health_weight_crud.get_all_health_weight_by_user_id(
        user_id, db
    )

    # Check if health data entries
    if health_weight_entries:
        # Loop through all the health data entries and calculate the bmi
        for health_weight in health_weight_entries:
            aux_health_weight = health_weight_schema.HealthWeight(
                id=health_weight.id,
                user_id=health_weight.user_id,
                date=health_weight.date,
                weight=health_weight.weight,
                bmi=health_weight.bmi,
                source=health_weight.source,
            )
            aux_health_weight = calculate_bmi(aux_health_weight, user_id, db)
            health_weight_crud.edit_health_weight(user_id, aux_health_weight, db)
