from sqlalchemy.orm import Session

import users.user.crud as users_crud

import health_data.schema as health_data_schema
import health_data.crud as health_data_crud


def calculate_bmi(
    health_data: health_data_schema.HealthData,
    user_id: int,
    db: Session,
) -> health_data_schema.HealthData:
    # Get the user from the database
    user = users_crud.get_user_by_id(user_id, db)

    # Check if user is not None and user height is not None
    if user is not None and user.height is not None:
        # Calculate the bmi
        health_data.bmi = float(health_data.weight) / ((user.height / 100) ** 2)
    else:
        if user.height is None:
            health_data.bmi = None

    # return the health data
    return health_data


def calculate_bmi_all_user_entries(user_id: int, db: Session):
    # Get all the health data entries for the user
    health_data_entries = health_data_crud.get_all_health_data_by_user_id(user_id, db)

    # Check if health data entries
    if health_data_entries:
        # Loop through all the health data entries and calculate the bmi
        for health_data in health_data_entries:
            aux_health_data = health_data_schema.HealthData(
                id=health_data.id,
                user_id=health_data.user_id,
                date=health_data.date,
                weight=health_data.weight,
                bmi=health_data.bmi,
                garminconnect_body_composition_id=health_data.garminconnect_body_composition_id,
            )
            aux_health_data = calculate_bmi(aux_health_data, user_id, db)
            health_data_crud.edit_health_data(user_id, aux_health_data, db)
