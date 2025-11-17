from fastapi import HTTPException
from sqlalchemy.orm import Session

import users.user_default_gear.crud as user_default_gear_crud


def get_user_default_gear_by_activity_type(
    user_id: int, activity_type: int, db: Session
) -> int | None:
    try:
        user_default_gear = user_default_gear_crud.get_user_default_gear_by_user_id(
            user_id, db
        )

        if activity_type == 1:
            return user_default_gear.run_gear_id
        elif activity_type == 2:
            return user_default_gear.trail_run_gear_id
        elif activity_type == 3:
            return user_default_gear.virtual_run_gear_id
        elif activity_type == 4:
            return user_default_gear.ride_gear_id
        elif activity_type == 5:
            return user_default_gear.gravel_ride_gear_id
        elif activity_type == 6:
            return user_default_gear.mtb_ride_gear_id
        elif activity_type == 7:
            return user_default_gear.virtual_ride_gear_id
        elif activity_type == 9:
            return user_default_gear.ows_gear_id
        elif activity_type in (11, 31):
            return user_default_gear.walk_gear_id
        elif activity_type == 12:
            return user_default_gear.hike_gear_id
        elif activity_type == 15:
            return user_default_gear.alpine_ski_gear_id
        elif activity_type == 16:
            return user_default_gear.nordic_ski_gear_id
        elif activity_type == 17:
            return user_default_gear.snowboard_gear_id
        elif activity_type == 21:
            return user_default_gear.tennis_gear_id
        elif activity_type == 30:
            return user_default_gear.windsurf_gear_id
        else:
            return None
    except HTTPException as err:
        raise err
