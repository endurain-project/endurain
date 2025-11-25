from sqlalchemy.orm import Session

import users.user.crud as users_crud

import health_weight.schema as health_weight_schema
import health_weight.crud as health_weight_crud


def calculate_bmi(
    health_weight: health_weight_schema.HealthWeight,
    user_id: int,
    db: Session,
) -> health_weight_schema.HealthWeight:
    # Get the user from the database
    user = users_crud.get_user_by_id(user_id, db)

    # Check if user is not None and user height is not None
    if user is not None and user.height is not None:
        # Calculate the bmi
        health_weight.bmi = float(health_weight.weight) / ((user.height / 100) ** 2)
    else:
        # Set bmi to None if user doesn't exist or height is missing
        health_weight.bmi = None

    # return the health weight
    return health_weight


def calculate_bmi_all_user_entries(user_id: int, db: Session):
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
