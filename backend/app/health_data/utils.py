from sqlalchemy.orm import Session

import users.crud as users_crud

import health_data.schema as health_data_schema

def calculate_bmi(health_data: health_data_schema.HealthData, user_id: int, db: Session):
    # Get the user from the database
    user = users_crud.get_user_by_id(user_id, db)

    # Check if user is not None and user height is not None
    if user is not None and user.height is not None:
        # Calculate the bmi
        health_data.bmi = health_data.weight / ((user.height / 100) ** 2)

    # return the health data
    return health_data