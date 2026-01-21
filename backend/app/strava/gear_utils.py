import os
import csv
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from stravalib.client import Client

import core.config as core_config
import core.logger as core_logger

import strava.utils as strava_utils
import strava.athlete_utils as strava_athlete_utils

import gears.gear.schema as gears_schema
import gears.gear.crud as gears_crud
import gears.gear.utils as gears_utils

import activities.activity.schema as activities_schema
import activities.activity.crud as activities_crud

import users.users_integrations.crud as user_integrations_crud

from core.database import SessionLocal


def get_strava_gear(gear_id: str, strava_client: Client):
    # Fetch Strava gear
    try:
        strava_gear = strava_client.get_gear(gear_id)
    except Exception as err:
        # Log an error event if the gear could not be fetched
        core_logger.print_to_log(
            f"Error fetching Strava gear with ID: {err}. Returning 424 Failed Dependency",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Not able to fetch Strava gear",
        ) from err

    if strava_gear is None:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Not able to fetch Strava gear",
        )

    return strava_gear


def fetch_and_process_gear(strava_client: Client, user_id: int, db: Session) -> int:
    # Fetch Strava athlete
    try:
        strava_athlete = strava_athlete_utils.get_strava_athlete(strava_client)
    except Exception as err:
        raise err

    # Initialize an empty list for results
    strava_gear = []

    # Store the athlete's bikes
    athlete_bikes = strava_athlete.bikes
    athlete_shoes = strava_athlete.shoes

    for bike in athlete_bikes:
        strava_gear.append(process_gear(bike, "bike", user_id, strava_client, db))

    for shoe in athlete_shoes:
        strava_gear.append(process_gear(shoe, "shoe", user_id, strava_client, db))

    if strava_gear is None:
        # Log an informational event if no gear were found
        core_logger.print_to_log(
            f"User {user_id}: No new Strava gear found: strava_gear is None"
        )

        # Return 0 to indicate no gear were processed
        return 0

    # Save the gear to the database
    gears_crud.create_multiple_gears(strava_gear, user_id, db)

    # Return the number of activities processed
    return len(strava_gear)


def process_gear(
    gear, gear_type: str, user_id: int, strava_client: Client, db: Session
) -> gears_schema.Gear | None:
    # Get the gear by strava id from user id
    gear_db = gears_crud.get_gear_by_strava_id_from_user_id(gear.id, user_id, db)

    # Skip existing gear
    if gear_db:
        return None

    # Get the gear from Strava
    try:
        strava_gear = get_strava_gear(gear.id, strava_client)
    except Exception as err:
        raise err

    new_gear = gears_schema.Gear(
        brand=strava_gear.brand_name,
        model=strava_gear.model_name,
        nickname=strava_gear.name,
        gear_type=1 if gear_type == "bike" else 2,
        user_id=user_id,
        active=True,
        strava_gear_id=gear.id,
    )

    return new_gear


def iterate_over_activities_and_set_gear(
    activity: activities_schema.Activity, gears: list[gears_schema.Gear], counter: int
) -> dict:

    # Iterate over gears and set gear if applicable
    if activity.strava_gear_id is not None:
        for gear in gears:
            if activity.strava_gear_id == gear.strava_gear_id:
                activity.gear_id = gear.id
                counter += 1
                break

    # Return the counter
    return {"counter": counter, "activity": activity}


def set_activities_gear(user_id: int, db: Session) -> int:
    # Get user activities
    activities = activities_crud.get_user_activities(user_id, db)

    # Skip if no activities
    if activities is None:
        return 0

    # Get user gears
    gears = gears_crud.get_gear_user(user_id, db)

    # Skip if no gears
    if gears is None:
        return 0

    # Initialize a counter
    counter = 0

    # Initialize an empty list for results
    activities_parsed = []

    # iterate over activities and set gear if applicable
    for activity in activities:
        parsed_activity = iterate_over_activities_and_set_gear(activity, gears, counter)
        counter = parsed_activity["counter"]
        activities_parsed.append(parsed_activity["activity"])

    activities_crud.edit_multiple_activities_gear_id(activities_parsed, user_id, db)

    return counter


def get_user_gear(user_id: int):
    # Create a new database session using context manager
    with SessionLocal() as db:
        # Get the user integrations by user ID
        user_integrations = strava_utils.fetch_user_integrations_and_validate_token(
            user_id, db
        )

        # Log the start of the activities processing
        core_logger.print_to_log(f"User {user_id}: Started Strava gear processing")

        # Create a Strava client with the user's access token
        strava_client = strava_utils.create_strava_client(user_integrations)

        # Set the user's gear to sync to True
        user_integrations_crud.set_user_strava_sync_gear(user_id, True, db)

        # Fetch Strava gear
        num_strava_gear_processed = fetch_and_process_gear(strava_client, user_id, db)

        # Log an informational event for tracing
        core_logger.print_to_log(
            f"User {user_id}: {num_strava_gear_processed} Strava gear processed"
        )

        # Log an informational event for tracing
        core_logger.print_to_log(
            f"User {user_id}: Will parse current activities and set gear if applicable"
        )

        num_gear_activities_set = set_activities_gear(user_id, db)

        # Log an informational event for tracing
        core_logger.print_to_log(
            f"User {user_id}: {num_gear_activities_set} activities where gear was set"
        )


def iterate_over_bikes_csv() -> dict:
    """
    Parses a Strava bikes CSV file and returns its contents as a dictionary.

    The function looks for a CSV file specified by configuration settings, reads it, and constructs a dictionary where each key is the "Bike Name" from the CSV, and the value is a dictionary of the bike's attributes as provided in the CSV row.

    Returns:
        dict: A dictionary mapping bike names to their corresponding data from the CSV file.

    Raises:
        HTTPException: If the CSV file is missing, has invalid headers, or cannot be parsed.
    """
    # CSV file location
    bulk_import_dir = core_config.FILES_BULK_IMPORT_DIR
    bikes_file_name = core_config.STRAVA_BULK_IMPORT_BIKES_FILE
    bikes_file_path = os.path.join(bulk_import_dir, bikes_file_name)

    # Get file and parse it
    bikes_dict = {}
    try:
        if os.path.isfile(bikes_file_path):
            core_logger.print_to_log_and_console(
                f"{bikes_file_name} exists in the {bulk_import_dir} directory. Starting to process file."
            )
            with open(bikes_file_path, "r", encoding="utf-8") as bike_file:
                bikes_csv = csv.DictReader(bike_file)
                for row in bikes_csv:
                    if (
                        ("Bike Name" not in row)
                        or ("Bike Brand" not in row)
                        or ("Bike Model" not in row)
                    ):
                        core_logger.print_to_log_and_console(
                            f"Aborting bikes import: Proper headers not found in {bikes_file_name}.  File should have 'Bike Name', 'Bike Brand', and 'Bike Model'."
                        )
                        raise HTTPException(
                            status_code=status.HTTP_424_FAILED_DEPENDENCY,
                            detail="Invalid file. Proper headers not found in Strava bikes CSV file.",
                        )
                    bikes_dict[row["Bike Name"]] = row
            core_logger.print_to_log_and_console(
                f"Strava bike gear csv file parsed and gear dictionary created. File was {len(bikes_dict)} rows long, ignoring header row."
            )
            return bikes_dict
        core_logger.print_to_log_and_console(
            f"No {bikes_file_name} file located in the {bulk_import_dir} directory."
        )
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="No Strava bikes CSV file found for import.",
        )
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        core_logger.print_to_log_and_console(
            f"Error attempting to open {bikes_file_path} file:  {err}", "error"
        )
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Error parsing Strava bikes CSV file.",
        ) from err


def iterate_over_shoes_csv() -> list:
    """
    Parses a Strava shoes CSV file and returns its contents as a list.
    Why a list?  Strava shoes files do not have anything that can be used as a key (unlike Strava bikes files, where nickname is required and unique)

    The function looks for a CSV file specified by configuration settings, reads it, and constructs a list where each item a dictionary of the shoe's attributes as provided in the CSV row.

    Returns:
        list: A list of shoe data obtained from the CSV file.

    Raises:
        HTTPException: If the CSV file is missing, has invalid headers, or cannot be parsed.
    """
    # CSV file location
    bulk_import_dir = core_config.FILES_BULK_IMPORT_DIR
    shoesfilename = core_config.STRAVA_BULK_IMPORT_SHOES_FILE
    shoes_file_path = os.path.join(bulk_import_dir, shoesfilename)

    # Get file and parse it
    shoes_list = (
        []
    )  # Using a list for shoes, as there is no unique value to use as a dictionary key like with bikes
    try:
        if os.path.isfile(shoes_file_path):
            core_logger.print_to_log_and_console(
                f"{shoesfilename} exists in the {bulk_import_dir} directory. Starting to process file."
            )
            with open(shoes_file_path, "r", encoding="utf-8") as shoe_file:
                shoes_csv = csv.DictReader(shoe_file)
                for row in shoes_csv:
                    if (
                        ("Shoe Name" not in row)
                        or ("Shoe Brand" not in row)
                        or ("Shoe Model" not in row)
                    ):
                        core_logger.print_to_log_and_console(
                            f"Aborting shoes import: Proper headers not found in {shoesfilename}. File should have 'Shoe Name', 'Shoe Brand', and 'Shoe Model'."
                        )
                        raise HTTPException(
                            status_code=status.HTTP_424_FAILED_DEPENDENCY,
                            detail="Invalid file. Proper headers not found in Strava shoes CSV file.",
                        )
                    shoes_list.append(row)
            core_logger.print_to_log_and_console(
                f"Strava {shoesfilename} file parsed and gear dictionary created. File was {len(shoes_list)} rows long, ignoring header row."
            )
            return shoes_list
        core_logger.print_to_log_and_console(
            f"No {shoesfilename} file located in the {bulk_import_dir} directory."
        )
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="No Strava shoes CSV file found for import.",
        )
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        core_logger.print_to_log_and_console(
            f"Error attempting to open {shoes_file_path} file:  {err}", "error"
        )
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Error parsing Strava shoes CSV file.",
        ) from err


def transform_csv_bike_gear_to_schema_gear(
    bikes_dict: dict, token_user_id: int
) -> list[gears_schema.Gear]:
    """
    Transforms a dictionary of bike data (parsed from CSV) into a list of Gear schema objects.

    Args:
        bikes_dict (dict): A dictionary where each key is a bike nickname and each value is a dictionary
            containing bike attributes such as "Bike Brand" and "Bike Model".
        token_user_id (int): The user ID to associate with each Gear object.

    Returns:
        list[gears_schema.Gear]: A list of Gear schema objects created from the input bike data.
    """
    gears = []
    for bike in bikes_dict:
        new_gear = gears_schema.Gear(
            user_id=token_user_id,
            brand=bikes_dict[bike]["Bike Brand"],
            model=bikes_dict[bike]["Bike Model"],
            nickname=bike,
            gear_type=gears_utils.GEAR_NAME_TO_ID["bike"],
            active=True,
            strava_gear_id=None,
        )
        gears.append(new_gear)
    return gears


def transform_csv_shoe_gear_to_schema_gear(
    shoes_list: list, token_user_id: int, db: Session
) -> list[gears_schema.Gear]:
    """
    Transforms a list of shoe data (parsed from CSV) into a list of Gear schema objects.
    Renames any name-less shoes to a default name plus a unique number, as Strava allows name-less shoes, but Endurain does not.

    Args:
        shoes_list (list): A list where each row is a single shoe's data, parsed from the strava shoe csv
        token_user_id (int): The user ID to associate with each Gear object.
        db (session): Database session

    Returns:
        list[gears_schema.Gear]: A list of Gear schema objects created from the input shoe data.
    """
    gears = []
    newnumber = 1
    for shoerow in shoes_list:
        # 1 - Check for nameless shoes and add a novel name. Why?  Because Strava allows nameless shoes, but Endurain does not.
        if (
            shoerow["Shoe Name"] is None
            or shoerow["Shoe Name"] == ""
            or shoerow["Shoe Name"].replace("+", " ").strip() == ""
        ):
            # Shoe name is blank or parses to blank; assign a new, non-duplicated name.
            proposed_name_is_already_present = True
            while proposed_name_is_already_present:
                proposed_name = core_config.STRAVA_BULK_IMPORT_SHOES_UNNAMED_SHOE + str(
                    newnumber
                )
                gear_check = gears_crud.get_gear_user_by_nickname(
                    token_user_id, proposed_name, db
                )
                if gear_check is not None:
                    newnumber += 1
                else:
                    proposed_name_is_already_present = False
                    shoe_name = proposed_name
                    core_logger.print_to_log_and_console(
                        f"Shoe name was blank, it has been updated to: {proposed_name}"
                    )
                    newnumber += 1  # Iterate the number so the next unnamed shoe does not duplicate this one.
        else:
            # CSV data has a name for the shoe, use CSV's data as the name.
            shoe_name = shoerow["Shoe Name"]

        # 2 - Add (possibly renamed) gear item to the list of gear to be added.
        new_gear = gears_schema.Gear(
            user_id=token_user_id,
            brand=shoerow["Shoe Brand"],
            model=shoerow["Shoe Model"],
            nickname=shoe_name,
            gear_type=gears_utils.GEAR_NAME_TO_ID["shoes"],
            active=True,
            strava_gear_id=None,
        )
        gears.append(new_gear)
    return gears
