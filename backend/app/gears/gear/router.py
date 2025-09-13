from typing import Annotated, Callable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Security
from sqlalchemy.orm import Session

import session.security as session_security

import gears.gear.schema as gears_schema
import gears.gear.utils as gears_utils
import gears.gear.crud as gears_crud
import gears.gear.dependencies as gears_dependencies

import core.database as core_database
import core.logger as core_logger
import core.config as core_config

import users.user.dependencies as users_dependencies

import os
import csv
from datetime import datetime

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=list[gears_schema.Gear] | None,
)
async def read_gears(
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["gears:read"])
    ],
    token_user_id: Annotated[
        int, Depends(session_security.get_user_id_from_access_token)
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    # Return the gear
    return gears_crud.get_gear_user(token_user_id, db)


@router.get(
    "/id/{gear_id}",
    response_model=gears_schema.Gear | None,
)
async def read_gear_id(
    gear_id: int,
    validate_gear_id: Annotated[Callable, Depends(gears_dependencies.validate_gear_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["gears:read"])
    ],
    token_user_id: Annotated[
        int, Depends(session_security.get_user_id_from_access_token)
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    # Return the gear
    return gears_crud.get_gear_user_by_id(token_user_id, gear_id, db)


@router.get(
    "/page_number/{page_number}/num_records/{num_records}",
    response_model=list[gears_schema.Gear] | None,
)
async def read_gear_user_pagination(
    page_number: int,
    num_records: int,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["gears:read"])
    ],
    token_user_id: Annotated[
        int, Depends(session_security.get_user_id_from_access_token)
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Return the gear
    return gears_crud.get_gear_users_with_pagination(
        token_user_id, db, page_number, num_records
    )


@router.get(
    "/number",
    response_model=int,
)
async def read_gear_user_number(
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["gears:read"])
    ],
    token_user_id: Annotated[
        int, Depends(session_security.get_user_id_from_access_token)
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the gear
    gear = gears_crud.get_gear_user(token_user_id, db)

    # Check if gear is None and return 0 if it is
    if gear is None:
        return 0

    # Return the number of gears
    return len(gear)


@router.get(
    "/nickname/contains/{nickname}",
    response_model=list[gears_schema.Gear] | None,
)
async def read_gear_user_contains_nickname(
    nickname: str,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["gears:read"])
    ],
    token_user_id: Annotated[
        int, Depends(session_security.get_user_id_from_access_token)
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Return the gears
    return gears_crud.get_gear_user_contains_nickname(token_user_id, nickname, db)


@router.get(
    "/nickname/{nickname}",
    response_model=gears_schema.Gear | None,
)
async def read_gear_user_by_nickname(
    nickname: str,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["gears:read"])
    ],
    token_user_id: Annotated[
        int, Depends(session_security.get_user_id_from_access_token)
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Return the gear
    return gears_crud.get_gear_user_by_nickname(token_user_id, nickname, db)


@router.get(
    "/type/{gear_type}",
    response_model=list[gears_schema.Gear] | None,
)
async def read_gear_user_by_type(
    gear_type: int,
    validate_type: Annotated[Callable, Depends(gears_dependencies.validate_gear_type)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["gears:read"])
    ],
    token_user_id: Annotated[
        int, Depends(session_security.get_user_id_from_access_token)
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Return the gear
    return gears_crud.get_gear_by_type_and_user(gear_type, token_user_id, db)


@router.post(
    "",
    response_model=gears_schema.Gear,
    status_code=201,
)
async def create_gear(
    gear: gears_schema.Gear,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["gears:write"])
    ],
    token_user_id: Annotated[
        int, Depends(session_security.get_user_id_from_access_token)
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Create the gear and return it
    return gears_crud.create_gear(gear, token_user_id, db)


@router.put("/{gear_id}")
async def edit_gear(
    gear_id: int,
    validate_id: Annotated[Callable, Depends(gears_dependencies.validate_gear_id)],
    gear: gears_schema.Gear,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["gears:write"])
    ],
    token_user_id: Annotated[
        int, Depends(session_security.get_user_id_from_access_token)
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the gear by id
    gear_db = gears_crud.get_gear_user_by_id(token_user_id, gear_id, db)

    # Check if gear is None and raise an HTTPException if it is
    if gear_db is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gear ID {gear_id} not found",
        )

    if gear_db.user_id != token_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Gear ID {gear_id} does not belong to user {token_user_id}",
        )

    # Edit the gear
    gears_crud.edit_gear(gear_id, gear, db)

    # Return success message
    return {"detail": f"Gear ID {gear_id} edited successfully"}


@router.delete("/{gear_id}")
async def delete_gear(
    gear_id: int,
    validate_id: Annotated[Callable, Depends(gears_dependencies.validate_gear_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["gears:write"])
    ],
    token_user_id: Annotated[
        int, Depends(session_security.get_user_id_from_access_token)
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the gear by id
    gear = gears_crud.get_gear_user_by_id(token_user_id, gear_id, db)

    # Check if gear is None and raise an HTTPException if it is
    if gear is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gear ID {gear_id} not found",
        )

    if gear.user_id != token_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Gear ID {gear_id} does not belong to user {token_user_id}",
        )

    # Delete the gear
    gears_crud.delete_gear(gear_id, db)

    # Return success message
    return {"detail": f"Gear ID {gear_id} deleted successfully"}


@router.post(
    "/stravabikesimport",
)
async def import_bikes_from_Strava_CSV(
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    background_tasks: BackgroundTasks,
):
    import_time_iso = datetime.today().date().strftime('%Y-%m-%d')
    try:
        core_logger.print_to_log("Entering bike importing function")

        # CSV file location
        bulk_import_dir = core_config.FILES_BULK_IMPORT_DIR
        bikesfilename = core_config.STRAVA_BULK_IMPORT_BIKES_FILE
        bikes_file_path = os.path.join(bulk_import_dir, bikesfilename)

        # Get file and parse it
        bikes_dict = {}  # format: "Bike Name" from the Strava CSV is used as the key, which then holds a dictionary that is based on the Strava bike gear CSV file's data
        try:
            if os.path.isfile(bikes_file_path):
                  core_logger.print_to_log_and_console(f"{bikesfilename} exists in the {bulk_import_dir} directory. Starting to process file.")
                  with open(bikes_file_path, "r") as bike_file:
                      bikes_csv = csv.DictReader(bike_file)
                      for row in bikes_csv:    # Must process CSV file object while file is still open.
                          # Example row: {'Bike Name': 'Ox', 'Bike Brand': 'Bianchi', 'Bike Model': 'Advantage', 'Bike Default Sport Types': 'Ride'}
                          if ('Bike Name' not in row) or ('Bike Brand' not in row) or ('Bike Model' not in row): 
                              core_logger.print_to_log_and_console(f"Aborting bikes import: Proper headers not found in {bikesfilename}.  File should have 'Bike Name', 'Bike Brand', and 'Bike Model'.")
                              return None
                          bikes_dict[row["Bike Name"]] = row
                  core_logger.print_to_log_and_console(f"Strava bike gear csv file parsed and gear dictionary created. File was {len(bikes_dict)} rows long, ignoring header row.")
            else:
                  core_logger.print_to_log_and_console(f"No {bikesfilename} file located in the {bulk_import_dir} directory.")
                  return None # Nothing to return - no file.
        except:
            # TO DO: RAISE ERROR OR ADD NOTIFICATON HERE?
            core_logger.print_to_log_and_console(f"Error attempting to open {bikes_file_path} file.")
            return None # Nothing to return - error parsing file.

        # Get user's existing gear 
        user_gear_list = gears_crud.get_gear_user(token_user_id, db)
            # Saving DB calls by doing this once for the entire gear import
            #   But one issue with pulling the DB before the import loop below: if a user's import has duplicate gear nicknames in it, this will not be caught by this check.
            #   But calling the get_gear_user function during the for loop below results in an error, and also would be tons of db calls for large gear imports.
            #   So, adding a duplicate-nickname check within a single import run to handle this case.

        # Create list of nicknames added during this import, to check for overlapping nicknames during this import (which causes an error)
        nicknames_added = []

        # Get gear type id of bikes
        bike_gear_type = gears_utils.GEAR_NAME_TO_ID["bike"]

        # Go through bikes and add them to the database if they are not duplicates.
        for bike in bikes_dict:  # bike here is the nickname of the bike from Strava (the index of our bikes_dict)
             gear_item_dict = {"name": bike, "brand": bikes_dict[bike]["Bike Brand"], "model": bikes_dict[bike]["Bike Model"], "gear_type": bike_gear_type}
             name_duplicated, gear_duplicated, duplicate_item = gears_utils.is_gear_duplicate(gear_item_dict, user_gear_list)
             if bike.replace("+", " ").lower() in nicknames_added: name_duplicated = True
             if name_duplicated:
                   # At least the nickname is duplicated, so do not import.  The following logic explains various cases to the user.
                   if gear_duplicated:
                       if duplicate_item.strava_gear_id is None:
                           core_logger.print_to_log_and_console(f"Bike - {bike} - found in existing user gear.  Skipping import.")
                       else:
                           core_logger.print_to_log_and_console(f"Bike - {bike} - was found in existing user gear, linked to Strava.  Skipping import of bike, but be aware that the bike will be removed if Strava is unlinked.")
                   else:
                       core_logger.print_to_log_and_console(f"Bike - {bike} - nickname of bike was found in existing user gear.  Skipping import, as nicknames cannot overlap (and capitalization does not matter).")
             else:
                   core_logger.print_to_log_and_console(f"Bike - {bike} - not found in existing user gear. Importing.")
                   # Notes on the import:
                   #     Strava does not export its internal gear ID, so we do not have that information.
                   #     Strava does not export the active / inactive state of the bike, so importing all as active (as we need a status).
                   new_gear = gears_schema.Gear(
                         user_id = token_user_id,
                         brand = bikes_dict[bike]["Bike Brand"],
                         model = bikes_dict[bike]["Bike Model"],
                         nickname = bike,
                         gear_type = bike_gear_type,
                         created_at = import_time_iso,
                         is_active = True,
                         strava_gear_id = None
                        )
                   added_gear = gears_crud.create_gear(new_gear, token_user_id, db)
                   core_logger.print_to_log_and_console(f"Bike - {bike} - has been imported as {added_gear.nickname}.")
                   nicknames_added.append(added_gear.nickname.lower()) # for checking of duplicated names during a single import, case-insenitively
        # Return a success message
        core_logger.print_to_log_and_console("Bike import complete.")
        return {"Gear import successful."}
    except Exception as err:
        # Log the exception
        core_logger.print_to_log_and_console(
            f"Error in import_bikes_from_Strava_CSV: {err}", "error"
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
