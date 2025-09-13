from sqlalchemy import func
from urllib.parse import unquote
from typing import Annotated
from fastapi import Depends
from sqlalchemy.orm import Session 
import session.security as session_security
import core.database as core_database

import gears.gear.models as gears_models
import gears.gear.crud as gears_crud
import gears.gear.schema as gears_schema

# Global gear type integer to gear name mapping (ID to name)
GEAR_ID_TO_NAME = {
    1: "bike",
    2: "shoes",
    3: "wetsuit",
    4: "racquet",
    5: "ski",
    6: "snowboard",
    7: "windsurf",
    8: "water_sports_board",
}

# Reverse gear type mapping, using the above-defined ID-to-name dictionary to create a name-to-ID dictionary
GEAR_NAME_TO_ID = {name.lower(): id for id, name in GEAR_ID_TO_NAME.items()}

# Space to add additional variations on gear names, for importing:
GEAR_NAME_TO_ID.update(
    {
        "bike": 1,
        "bicycle": 1,
        "shoes": 2,
        "racket": 4,
        "racquet": 4,
        "ski": 5,
        "skis": 5,
        "snowboard": 6,
        "windsurf": 7,
        "water_sports_board": 8,
        "surf_board": 8,
        "stand_up_paddling_board": 8,
    }
)

def transform_schema_gear_to_model_gear(
    gear: gears_schema.Gear, user_id: int
) -> gears_models.Gear:
    # Set the created date to now
    created_date = func.now()

    # If the created_at date is not None, set it to the created_date
    if gear.created_at is not None:
        created_date = gear.created_at

    # Create a new gear object
    #  Note - if the modifications to gear item nickname, brand, and model are altered (e.g., the + to space replace), be sure to simultaneously update the function is_gear_duplicate, below
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
        purchase_value=gear.purchase_value,
        strava_gear_id=gear.strava_gear_id,
        garminconnect_gear_id=gear.garminconnect_gear_id,
    )

    return new_gear


def serialize_gear(gear: gears_schema.Gear):
    # Serialize the gear object
    gear.created_at = gear.created_at.strftime("%Y-%m-%d")

    # Return the serialized gear object
    return gear

# Determine if a gear item is already in the gear database
    # Can use passed user gear list to save on calls to the database
    # Gear item dictionary struture:  gear_item = {"name": str, "brand": str, "model": str, "gear_type": int}
def is_gear_duplicate(
    gear_item: dict, 
    user_gear_list: list = None,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ] = None,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ] = None,
) -> tuple[bool, bool, gears_schema.Gear]:

    name_duplicate = False
    gear_is_duplicate = False
    duplicate_gear_item = None

    # Get gear list, if needed
    if user_gear_list == None:
        user_gear_list = gears_crud.get_gear_user(token_user_id, db)

    # Return no match if user has no gear
    if user_gear_list == None:
        return name_duplicate, gear_is_duplicate, duplicate_gear_item

    # Iterate through user gear list and look for an item that matches
    for item in user_gear_list:
        # Must replace + with space when checking becuase gear.utils.transform_schema_gear_to_model_gear modifies the entered gear name/model/brand when adding it to the database
        # Making all comparisons lower case, as Endrain gear database throws an error if names are the same with only capitalization differences
        # Checking both for name overlaps (which are not allowed, even for different gear types) and full item match.
        if item.nickname.lower() == gear_item["name"].replace("+", " ").lower():
            name_duplicate = True
            duplicate_gear_item = item
        if item.nickname.lower() == gear_item["name"].replace("+", " ").lower() and item.brand.lower() == gear_item["brand"].replace("+", " ").lower() and item.model.lower() == gear_item["model"].replace("+", " ").lower() and item.gear_type == gear_item["gear_type"]:
            name_duplicate = True
            gear_is_duplicate = True
            duplicate_gear_item = item
            break

    return name_duplicate, gear_is_duplicate, duplicate_gear_item

