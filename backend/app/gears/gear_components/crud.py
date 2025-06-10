from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from urllib.parse import unquote

import gears.gear_components.schema as gear_components_schema
import gears.gear_components.utils as gear_components_utils
import gears.gear_components.models as gear_components_models

import core.logger as core_logger


def get_gear_components_user(
    user_id: int, db: Session
) -> list[gear_components_schema.GearComponents] | None:
    try:
        # Get the gear components by user ID from the database
        gear_components = (
            db.query(gear_components_models.Gear)
            .filter(gear_components_models.Gear.user_id == user_id)
            .all()
        )

        # Check if gear components is None and return None if it is
        if gear_components is None:
            return None

        # Serialize the gear components
        for g in gear_components:
            g = gear_components_utils.serialize_gear_component(g)

        # Return the gear components
        return gear_components
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_gear_components_user: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
