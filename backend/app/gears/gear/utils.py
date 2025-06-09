from sqlalchemy import func
from urllib.parse import unquote

import gears.gear.models as gears_models
import gears.gear.schema as gears_schema


def transform_schema_gear_to_model_gear(
    gear: gears_schema.Gear, user_id: int
) -> gears_models.Gear:
    # Set the created date to now
    created_date = func.now()

    # If the created_at date is not None, set it to the created_date
    if gear.created_at is not None:
        created_date = gear.created_at

    # Create a new gear object
    new_gear = gears_models.Gear(
        brand=(
            unquote(gear.brand).replace("+", " ") if gear.brand is not None else None
        ),
        model=(
            unquote(gear.model).replace("+", " ") if gear.model is not None else None
        ),
        nickname=unquote(gear.nickname).replace("+", " "),
        gear_type=gear.gear_type,
        user_id=user_id,
        created_at=created_date,
        is_active=gear.is_active,
        initial_kms=gear.initial_kms,
        strava_gear_id=gear.strava_gear_id,
        garminconnect_gear_id=gear.garminconnect_gear_id,
    )

    return new_gear


def serialize_gear(gear: gears_schema.Gear):
    # Serialize the gear object
    gear.created_at = gear.created_at.strftime("%Y-%m-%d")

    # Return the serialized gear object
    return gear
