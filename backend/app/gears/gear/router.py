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
        if user_gear_list is None:
             #User has no gear - we can just add our own straight up.
             users_existing_gear_nicknames = None
        else:
             #User has gear - we will need to check for duplicates.  So build a list of gear nicknames to check against, as Strava requires a name for bikes (unlike shoes).
             users_existing_gear_nicknames = []
             for item in user_gear_list:
                  users_existing_gear_nicknames.append(item.nickname)

        # Get gear type id of bikes
        bike_gear_type = gears_utils.GEAR_NAME_TO_ID["bike"]

        # Go through bikes and add them to the database if they are not duplicates.
        for bike in bikes_dict:  # bike here is the nickname of the bike from Strava (the index of our bikes_dict)
             if bike in users_existing_gear_nicknames:
                   core_logger.print_to_log_and_console(f"Bike - {bike} - found in existing user gear (nicknames matched).  Skipping import.")
             else:
                   core_logger.print_to_log_and_console(f"Bike - {bike} - not found in existing user gear. Importing.")
                   # Notes on the import:
                   # Strava does not export its internal gear ID, so we do not have that information.
                   # Strava does not export the active / inactive state of the bike, so importing all as active (as we need a status).
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
                   gears_crud.create_gear(new_gear, token_user_id, db)
                   core_logger.print_to_log_and_console(f"Bike - {bike} - has been imported.")
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

@router.post(
    "/stravashoesimport",
)
async def import_shoes_from_Strava_CSV(
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
        core_logger.print_to_log("Entering shoe importing function")

        # CSV file location
        bulk_import_dir = core_config.FILES_BULK_IMPORT_DIR
        shoesfilename = core_config.STRAVA_BULK_IMPORT_SHOES_FILE
        shoes_file_path = os.path.join(bulk_import_dir, shoesfilename)

        # Get file and parse it
        shoes_list = [] # Using a list for shoes, as there is no unique value to use as a dictionary key like with bikes
        try:
            if os.path.isfile(shoes_file_path):
                  core_logger.print_to_log_and_console(f"{shoesfilename} exists in the {bulk_import_dir} directory. Starting to process file.")
                  with open(shoes_file_path, "r") as shoe_file:
                      shoes_csv = csv.DictReader(shoe_file)
                      for row in shoes_csv:    # Must process CSV file object while file is still open.
                          # Example row: {'Shoe Name': 'New forest runners', 'Shoe Brand': 'Saucony', 'Shoe Model': 'Trail runner 2200', 'Shoe Default Sport Types': ''}
                          if ('Shoe Name' not in row) or ('Shoe Brand' not in row) or ('Shoe Model' not in row): 
                              core_logger.print_to_log_and_console("Aborting shoes import: Proper headers not found in {shoesfilename}. File should have 'Shoe Name', 'Shoe Brand', and 'Shoe Model'.")
                              return None
                          shoes_list.append(row)
                  core_logger.print_to_log_and_console(f"Strava shoe gear csv file parsed and gear dictionary created. File was {len(shoes_list)} rows long, ignoring header row.")
            else:
                  core_logger.print_to_log_and_console(f"No {shoesfilename} file located in the {bulk_import_dir} directory.")
                  return None # Nothing to return - no file.
        except:
            # TO DO: RAISE ERROR OR ADD NOTIFICATON HERE?
            core_logger.print_to_log_and_console(f"Error attempting to open {shoes_file_path} file.")
            return None # Nothing to return - error parsing file.

        #core_logger.print_to_log_and_console(f"Users full shoe list is: {shoes_list}") # Testing code

        # Get user's existing gear 
        user_gear_list = gears_crud.get_gear_user(token_user_id, db)
        if user_gear_list is None:
             #User has no gear - we can just add our own straight up.
             users_existing_gear_dictionary = None
        else:
             #User has gear - we will need to check for duplicates.  So build a list of gear nicknames to check against.
             users_existing_gear_dictionary_list = []
             users_existing_gear_nicknames = []
             for item in user_gear_list:
                  gear_dict = {}
                  gear_dict["nickname"] = item.nickname
                  gear_dict["brand"] = item.brand
                  gear_dict["model"] = item.model
                  gear_dict["strava_gear_id"] = item.strava_gear_id
                  users_existing_gear_dictionary_list.append(gear_dict)
                  users_existing_gear_nicknames.append(item.nickname)
        #core_logger.print_to_log_and_console(f"User gear dictionary list: {users_existing_gear_dictionary_list}") # Testing code

        # Get gear type id of shoes
        shoe_gear_type = gears_utils.GEAR_NAME_TO_ID["shoes"]

        # Go through shoes and add them to the database if they are not duplicates.
        for shoerow in shoes_list:  # shoe here is list item that contains the dictionary from strava
             #core_logger.print_to_log_and_console(f"In shoes_dict iterator.  Current shoe is - {shoerow}") # Testing code.

             # Strava allows nameless shoes, but Endurain does not.  Check for nameless shoes and add a novel name.
             blank_name = False
             if shoerow["Shoe Name"] == None or shoerow["Shoe Name"] == "" or shoerow["Shoe Name"].replace("+", " ").strip() == "":
                   core_logger.print_to_log_and_console(f"Shoe name is blank") # Testing code
                   blank_name = True
                   duplicate_name = True
                   newnumber=1
                   while duplicate_name:
                         proposed_name = core_config.STRAVA_BULK_IMPORT_SHOES_UNNAMED_SHOE + str(newnumber)
                         if proposed_name in users_existing_gear_nicknames:
                               newnumber+=1
                         else:
                               duplicate_name = False
                   core_logger.print_to_log_and_console(f"Shoe name was blank, it has been updated to: {proposed_name}") # Testing code

             # Iterate through user gear list to check if shoe is already present
             #   Note - shoes that have a blank name in Strava and that have already been imported once will NOT be detected as duplicates, as the name will have been changed from the (blank) strava name.
             shoerowalreadypresent = False
             for item in users_existing_gear_dictionary_list:
                   # Must replace + with space when checking becuase gear.utils.transform_schema_gear_to_model_gear modifies the entered gear name/model/brand when adding it to the database
                   if item["nickname"] == shoerow["Shoe Name"].replace("+", " ") and item["brand"] == shoerow["Shoe Brand"].replace("+", " ") and item["model"] == shoerow["Shoe Model"].replace("+", " "):
                         if item["strava_gear_id"] == None:
                               shoerowalreadypresent = True
                               break
                         else:
                               # TO DO: Consider what to do in the case that the shoe exists, but it is from Strava. 
                               core_logger.print_to_log_and_console(f"Shoe - {shoerow} - found in existing gear, linked to Strava.  Not importing shoe, but be aware that shoe will be removed if Strava is unlinked.")
                               shoerowalreadypresent = True
                               break
             if shoerowalreadypresent:
                   core_logger.print_to_log_and_console(f"Shoe - {shoerow} - found in existing user gear.  Skipping import.")
             else:
                   core_logger.print_to_log_and_console(f"Shoe - {shoerow} - not found in existing user gear. Importing.")
                   # Notes on the import:
                   # Strava does not export its internal gear ID, so we do not have that information.
                   # Strava does not export the active / inactive state of the shoe, so importing all as active (as we need a status).
                   if blank_name:
                         shoe_name = proposed_name
                   else:
                         shoe_name = shoerow["Shoe Name"]
                   new_gear = gears_schema.Gear(
                         user_id = token_user_id,
                         brand = shoerow["Shoe Brand"],
                         model = shoerow["Shoe Model"],
                         nickname = shoe_name,
                         gear_type = shoe_gear_type,
                         created_at = import_time_iso,
                         is_active = True,
                         strava_gear_id = None
                        )
                   gears_crud.create_gear(new_gear, token_user_id, db)
                   core_logger.print_to_log_and_console(f"Shoe - {shoerow} - has been imported.")
        # Return a success message
        core_logger.print_to_log_and_console("Shoe import complete.")
        return {"Shoe import successful."}
    except Exception as err:
        # Log the exception
        core_logger.print_to_log_and_console(
            f"Error in import_shoes_from_Strava_CSV: {err}", "error"
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
