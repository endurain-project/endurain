"""User default gear utility functions."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

import core.logger as core_logger

import users.user_default_gear.crud as user_default_gear_crud

# Activity type to gear attribute mapping
ACTIVITY_TYPE_TO_GEAR_ATTR: dict[int, str] = {
    1: "run_gear_id",
    2: "trail_run_gear_id",
    3: "virtual_run_gear_id",
    4: "ride_gear_id",
    5: "gravel_ride_gear_id",
    6: "mtb_ride_gear_id",
    7: "virtual_ride_gear_id",
    9: "ows_gear_id",
    11: "walk_gear_id",
    12: "hike_gear_id",
    15: "alpine_ski_gear_id",
    16: "nordic_ski_gear_id",
    17: "snowboard_gear_id",
    21: "tennis_gear_id",
    30: "windsurf_gear_id",
    31: "walk_gear_id",  # Alias for walk
}


def get_user_default_gear_by_activity_type(
    user_id: int,
    activity_type: int,
    db: Session,
) -> int | None:
    """
    Get default gear ID for a specific activity type.

    Args:
        user_id: The ID of the user.
        activity_type: The activity type code.
        db: SQLAlchemy database session.

    Returns:
        The gear ID for the activity type, or None if not set
        or activity type is unknown.

    Raises:
        HTTPException: If user default gear not found or
            database error occurs.
    """
    try:
        user_default_gear = user_default_gear_crud.get_user_default_gear_by_user_id(
            user_id, db
        )

        if user_default_gear is None:
            return None

        attr_name = ACTIVITY_TYPE_TO_GEAR_ATTR.get(activity_type)
        if attr_name is None:
            return None

        return getattr(user_default_gear, attr_name, None)
    except HTTPException:
        raise
    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_user_default_gear_by_activity_type: {err}",
            "error",
            exc=err,
        )
        raise
