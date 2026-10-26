"""Strava gear: syncing the athlete's gear and importing a Strava export's gear CSVs."""

import os
import tempfile

from fastapi import UploadFile
from sqlalchemy.orm import Session
from stravalib.client import Client

import core.config as core_config
import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import core.text_imports as core_text_imports
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.gears.gear.integration_service as gears_integration
import modules.gears.gear.schema as gears_schema
import modules.strava.client_service as strava_client_service
import modules.users.users_integrations.integration_service as user_integrations_integration
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)

# Largest gear CSV accepted: a gear list is a few hundred rows at most.
_GEAR_CSV_MAX_BYTES = 2 * 1024 * 1024


def get_strava_gear(gear_id: str, strava_client: Client):
    """Fetch one piece of gear from Strava.

    Args:
        gear_id: The gear's Strava id.
        strava_client: A client authenticated as the user.

    Returns:
        The Strava gear.

    Raises:
        DependencyFailedError: When Strava cannot return the gear.
    """
    # Fetch Strava gear
    try:
        strava_gear = strava_client.get_gear(gear_id)
    except Exception as err:
        # Log an error event if the gear could not be fetched
        logger.error("Error fetching Strava gear", extra=core_logger.context(error=str(err)), exc_info=err)
        raise core_exceptions.DependencyFailedError("Not able to fetch Strava gear") from err

    if strava_gear is None:
        raise core_exceptions.DependencyFailedError("Not able to fetch Strava gear")

    return strava_gear


def get_strava_athlete(strava_client: Client):
    """Fetch the authenticated Strava athlete.

    Args:
        strava_client: A client authenticated as the user.

    Returns:
        The Strava athlete.

    Raises:
        DependencyFailedError: When Strava cannot return the athlete.
    """
    try:
        strava_athlete = strava_client.get_athlete()
    except Exception as err:
        logger.error("Error fetching Strava athlete", extra=core_logger.context(error=str(err)), exc_info=err)
        raise core_exceptions.DependencyFailedError("Error fetching Strava athlete") from err

    if strava_athlete is None:
        logger.error("Not able to fetch Strava athlete. Returning 424 Failed Dependency")
        raise core_exceptions.DependencyFailedError("Not able to fetch Strava athlete")

    return strava_athlete


def fetch_and_process_gear(strava_client: Client, user_id: int, db: Session) -> int:
    """Store the athlete's Strava bikes and shoes the user does not have yet.

    Args:
        strava_client: A client authenticated as the user.
        user_id: The user the gear belongs to.
        db: Database session.

    Returns:
        The number of gear entries handed to the gear module.
    """
    # Fetch Strava athlete
    strava_athlete = get_strava_athlete(strava_client)

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
        logger.info("No new Strava gear found", extra=core_logger.context(user_id=user_id))

        # Return 0 to indicate no gear were processed
        return 0

    # Save the gear to the database
    gears_integration.create_multiple_gears(strava_gear, user_id, db)
    db.commit()

    # Return the number of activities processed
    return len(strava_gear)


def process_gear(
    gear, gear_type: str, user_id: int, strava_client: Client, db: Session
) -> gears_schema.GearCreate | None:
    """Build the gear to create for one Strava gear entry.

    Args:
        gear: The athlete's gear summary from Strava.
        gear_type: ``"bike"`` or ``"shoe"``.
        user_id: The user the gear belongs to.
        strava_client: A client authenticated as the user.
        db: Database session.

    Returns:
        The gear to create, or ``None`` when the user already has it.
    """
    # Get the gear by strava id from user id
    gear_db = gears_integration.get_gear_by_strava_id(gear.id, user_id, db)

    # Skip existing gear
    if gear_db:
        return None

    # Get the gear from Strava
    strava_gear = get_strava_gear(gear.id, strava_client)

    new_gear = gears_schema.GearCreate(
        brand=strava_gear.brand_name,
        model=strava_gear.model_name,
        nickname=strava_gear.name,
        gear_type=(gears_schema.GearType.BIKE if gear_type == "bike" else gears_schema.GearType.SHOES),
        user_id=user_id,
        active=True,
        strava_gear_id=gear.id,
    )

    return new_gear


def match_gear_for_activity(
    activity: activity_schema.ActivityRead,
    gears: list[gears_schema.GearRead],
) -> int | None:
    """Return the local gear ID matching this activity's Strava gear, else None."""
    if activity.strava_gear_id is None:
        return None
    for gear in gears:
        if activity.strava_gear_id == gear.strava_gear_id:
            return gear.id
    return None


def set_activities_gear(user_id: int, db: Session) -> int:
    """Assign the user's Strava-linked activities to the matching local gear.

    Args:
        user_id: The user whose activities to update.
        db: Database session.

    Returns:
        The number of activities that were given gear.
    """
    # Get user activities
    activities = activity_integration.list_user_activities(user_id, db)

    # Skip if no activities
    if not activities:
        return 0

    # Get user gears
    gears = gears_integration.get_gear_user(user_id, db)

    # Skip if no gears
    if gears is None:
        return 0

    # Build {activity_id: gear_id} for all activities with a match
    gear_assignments: dict[int, int | None] = {}
    for activity in activities:
        matched_gear_id = match_gear_for_activity(activity, gears)
        if matched_gear_id is not None:
            gear_assignments[activity.id] = matched_gear_id

    # Persist via CRUD (single UPDATE per distinct gear_id)
    activity_integration.bulk_set_activities_gear(user_id, gear_assignments, db)
    db.commit()
    logger.debug("Strava activities gear set", extra=core_logger.context(user_id=user_id, count=len(gear_assignments)))

    return len(gear_assignments)


def get_user_gear(user_id: int) -> None:
    """Import the user's Strava gear and assign it to their activities.

    Runs in the background with a session of its own.

    Args:
        user_id: The user whose gear to import.
    """
    # Create a new database session using context manager
    with SessionLocal() as db:
        # Get the user integrations by user ID
        user_integrations = strava_client_service.fetch_user_integrations_and_validate_token(user_id, db)

        # Log the start of the activities processing
        logger.info("Started Strava gear processing", extra=core_logger.context(user_id=user_id))

        # Create a Strava client with the user's access token
        strava_client = strava_client_service.create_strava_client(user_integrations)

        # Set the user's gear to sync to True
        user_integrations_integration.set_strava_sync_gear(user_id, True, db)
        db.commit()

        # Fetch Strava gear
        num_strava_gear_processed = fetch_and_process_gear(strava_client, user_id, db)

        # Log an informational event for tracing
        logger.info(
            "Strava gear processed", extra=core_logger.context(user_id=user_id, count=num_strava_gear_processed)
        )

        # Log an informational event for tracing
        logger.info(
            "Will parse current activities and set gear if applicable", extra=core_logger.context(user_id=user_id)
        )

        num_gear_activities_set = set_activities_gear(user_id, db)

        # Log an informational event for tracing
        logger.info(
            "Activities had their gear set", extra=core_logger.context(user_id=user_id, count=num_gear_activities_set)
        )


def iterate_over_bikes_csv(bikes_file_path: str) -> dict:
    """Parses a Strava bikes CSV file and returns its contents as a dictionary.

    Constructs a dictionary where each key is the "Bike Name" from the CSV, and the value is a dictionary of the bike's attributes as provided in the CSV row.

    Args:
        bikes_file_path: Path of the uploaded bikes CSV.

    Returns:
        dict: A dictionary mapping bike names to their corresponding data from the CSV file.

    Raises:
        DependencyFailedError: If the CSV file is missing, has invalid headers, or cannot be parsed.
    """
    bikes_file_name = "bikes.csv"

    # Get file and parse it
    bikes_dict = {}
    try:
        if os.path.isfile(bikes_file_path):
            logger.info(
                "Parsing the uploaded gear CSV", extra=core_logger.context(console=True, file_name=bikes_file_name)
            )
            for row in core_text_imports.read_bounded_csv(bikes_file_path):
                if ("Bike Name" not in row) or ("Bike Brand" not in row) or ("Bike Model" not in row):
                    logger.info(
                        "Aborting bikes import: required headers not found (Bike Name, Bike Brand, Bike Model)",
                        extra=core_logger.context(console=True, file_name=bikes_file_name),
                    )
                    raise core_exceptions.DependencyFailedError(
                        "Invalid file. Proper headers not found in Strava bikes CSV file."
                    )
                bikes_dict[row["Bike Name"]] = row
            logger.info(
                "Strava bike gear CSV parsed", extra=core_logger.context(console=True, row_count=len(bikes_dict))
            )
            return bikes_dict
        logger.info(
            "No Strava bikes CSV file found for import.",
            extra=core_logger.context(console=True),
        )
        raise core_exceptions.DependencyFailedError("No Strava bikes CSV file found for import.")
    except core_exceptions.DomainError:
        raise
    except Exception as err:
        logger.error(
            "Error opening the bikes CSV",
            extra=core_logger.context(console=True, file_name=bikes_file_name, error=str(err)),
        )
        raise core_exceptions.DependencyFailedError("Error parsing Strava bikes CSV file.") from err


def iterate_over_shoes_csv(shoes_file_path: str) -> list:
    """Parse a Strava shoes CSV file and return its contents as a list.

    A list rather than a dictionary: Strava shoes files have nothing usable as a key,
    unlike bikes, where the nickname is required and unique.

    Constructs a list where each item a dictionary of the shoe's attributes as provided in the CSV row.

    Args:
        shoes_file_path: Path of the uploaded shoes CSV.

    Returns:
        list: A list of shoe data obtained from the CSV file.

    Raises:
        DependencyFailedError: If the CSV file is missing, has invalid headers, or cannot be parsed.
    """
    shoesfilename = "shoes.csv"

    # Get file and parse it
    shoes_list = []  # Using a list for shoes, as there is no unique value to use as a dictionary key like with bikes
    try:
        if os.path.isfile(shoes_file_path):
            logger.info(
                "Parsing the uploaded gear CSV", extra=core_logger.context(console=True, file_name=shoesfilename)
            )
            for row in core_text_imports.read_bounded_csv(shoes_file_path):
                if ("Shoe Name" not in row) or ("Shoe Brand" not in row) or ("Shoe Model" not in row):
                    logger.info(
                        "Aborting shoes import: required headers not found (Shoe Name, Shoe Brand, Shoe Model)",
                        extra=core_logger.context(console=True, file_name=shoesfilename),
                    )
                    raise core_exceptions.DependencyFailedError(
                        "Invalid file. Proper headers not found in Strava shoes CSV file."
                    )
                shoes_list.append(row)
            logger.info("Strava shoes CSV parsed", extra=core_logger.context(console=True, row_count=len(shoes_list)))
            return shoes_list
        logger.info(
            "No Strava shoes CSV file found for import.",
            extra=core_logger.context(console=True),
        )
        raise core_exceptions.DependencyFailedError("No Strava shoes CSV file found for import.")
    except core_exceptions.DomainError:
        raise
    except Exception as err:
        logger.error(
            "Error opening the shoes CSV",
            extra=core_logger.context(console=True, file_name=shoesfilename, error=str(err)),
        )
        raise core_exceptions.DependencyFailedError("Error parsing Strava shoes CSV file.") from err


def transform_csv_bike_gear_to_schema_gear(bikes_dict: dict, token_user_id: int) -> list[gears_schema.GearCreate]:
    """Transforms a dictionary of bike data (parsed from CSV) into a list of Gear schema objects.

    Args:
        bikes_dict (dict): A dictionary where each key is a bike nickname and each value is a dictionary
            containing bike attributes such as "Bike Brand" and "Bike Model".
        token_user_id (int): The user ID to associate with each Gear object.

    Returns:
        list[gears_schema.GearCreate]: A list of Gear schema objects created from the input bike data.
    """
    gears = []
    for bike in bikes_dict:
        new_gear = gears_schema.GearCreate(
            user_id=token_user_id,
            brand=bikes_dict[bike]["Bike Brand"].strip() if bikes_dict[bike]["Bike Brand"] else None,
            model=bikes_dict[bike]["Bike Model"].strip() if bikes_dict[bike]["Bike Model"] else None,
            nickname=bike.strip(),
            gear_type=gears_schema.GearType.BIKE,
            active=True,
            strava_gear_id=None,
        )
        gears.append(new_gear)
    return gears


def transform_csv_shoe_gear_to_schema_gear(
    shoes_list: list, token_user_id: int, db: Session
) -> list[gears_schema.GearCreate]:
    """Transform a list of shoe data (parsed from CSV) into a list of Gear schema objects.

    Renames any name-less shoes to a default name plus a unique number, as Strava allows name-less shoes, but Endurain does not.

    Args:
        shoes_list (list): A list where each row is a single shoe's data, parsed from the strava shoe csv
        token_user_id (int): The user ID to associate with each Gear object.
        db (session): Database session

    Returns:
        list[gears_schema.GearCreate]: A list of Gear schema objects created from the input shoe data.
    """
    gears = []
    newnumber = 1
    shoe_name = ""
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
                proposed_name = core_config.STRAVA_BULK_IMPORT_SHOES_UNNAMED_SHOE + str(newnumber)
                gear_check = gears_integration.get_gear_user_by_nickname(token_user_id, proposed_name, db)
                if gear_check is not None:
                    newnumber += 1
                else:
                    proposed_name_is_already_present = False
                    shoe_name = proposed_name
                    logger.info(
                        "Shoe name was blank, it has been renamed",
                        extra=core_logger.context(console=True, nickname=proposed_name),
                    )
                    newnumber += 1  # Iterate the number so the next unnamed shoe does not duplicate this one.
        else:
            # CSV data has a name for the shoe, use CSV's data as the name.
            shoe_name = shoerow["Shoe Name"].strip()

        # 2 - Add (possibly renamed) gear item to the list of gear to be added.
        new_gear = gears_schema.GearCreate(
            user_id=token_user_id,
            brand=shoerow["Shoe Brand"].strip() if shoerow["Shoe Brand"] else None,
            model=shoerow["Shoe Model"].strip() if shoerow["Shoe Model"] else None,
            nickname=shoe_name,
            gear_type=gears_schema.GearType.SHOES,
            active=True,
            strava_gear_id=None,
        )
        gears.append(new_gear)
    return gears


def _save_gear_csv(file: UploadFile) -> tuple[tempfile.TemporaryDirectory, str]:
    """Stream an uploaded gear CSV to a private temp directory.

    Args:
        file: The uploaded CSV.

    Returns:
        The temp directory (the caller closes it) and the saved file's path.
    """
    work_dir = tempfile.TemporaryDirectory(prefix="strava-gear-")
    try:
        path = core_file_uploads.save_text_upload_sync(
            file, upload_dir=work_dir.name, filename="gear.csv", max_bytes=_GEAR_CSV_MAX_BYTES
        )
    except BaseException:
        work_dir.cleanup()
        raise
    return work_dir, path


def import_bikes(file: UploadFile, user_id: int, db: Session) -> None:
    """Create the bikes listed in an uploaded Strava ``bikes.csv``.

    Args:
        file: The uploaded CSV.
        user_id: The user the bikes belong to.
        db: Database session.
    """
    work_dir, path = _save_gear_csv(file)
    try:
        bikes_dict = iterate_over_bikes_csv(path)
        bikes = transform_csv_bike_gear_to_schema_gear(bikes_dict, user_id) if bikes_dict else []
        if bikes:
            gears_integration.create_multiple_gears(bikes, user_id, db)
            db.commit()
        logger.info("Bike import complete.", extra=core_logger.context(console=True))
    finally:
        work_dir.cleanup()


def import_shoes(file: UploadFile, user_id: int, db: Session) -> None:
    """Create the shoes listed in an uploaded Strava ``shoes.csv``.

    Args:
        file: The uploaded CSV.
        user_id: The user the shoes belong to.
        db: Database session.
    """
    work_dir, path = _save_gear_csv(file)
    try:
        shoes_list = iterate_over_shoes_csv(path)
        shoes = transform_csv_shoe_gear_to_schema_gear(shoes_list, user_id, db) if shoes_list else []
        if shoes:
            gears_integration.create_multiple_gears(shoes, user_id, db)
            db.commit()
        logger.info("Shoe import complete.", extra=core_logger.context(console=True))
    finally:
        work_dir.cleanup()
