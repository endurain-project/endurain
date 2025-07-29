from typing import Annotated, Callable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Security
from sqlalchemy.orm import Session

import session.security as session_security

import gears.gear.schema as gears_schema
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
        bulk_import_dir = core_config.FILES_BULK_IMPORT_DIR

        # Hard coding filename for now (this is the filename Strava uses)
        bikesfilename = "bikes.csv"

        # Get file and parse it
        bikes_file_path = os.path.join(bulk_import_dir, bikesfilename)
        bikes_dict = {}  # format: "Bike Name" from the Strava CSV is used as the key, which then holds a dictionary that is based on the Strava bike gear CSV file's data
        try:
            if os.path.isfile(bikes_file_path):
                  core_logger.print_to_log_and_console(f"bikes.csv file exists in bulk_import directory. Starting to process file.")
                  with open(bikes_file_path, "r") as bike_file:
                      bikes_csv = csv.DictReader(bike_file)
                      for row in bikes_csv:    # Must process CSV file object while file is still open.
                          # Example row: {'Bike Name': 'Ox', 'Bike Brand': 'Bianchi', 'Bike Model': 'Advantage', 'Bike Default Sport Types': 'Ride'}
                          #print("Full row is", row) # Testing code
                          bikes_dict[row["Bike Name"]] = row
                          #print("Dicinotary row is: ", bikes_dict[row["Bike Name"]])  # Testing code
                          #print("Bike brand is: ", bikes_dict[row["Bike Name"]]["Bike Brand"]) # Testing code
                  core_logger.print_to_log_and_console(f"Strava bike gear csv file parsed and gear dictionary created. File was {len(bikes_dict)} rows long, ignoring header row.")
            else:
                  core_logger.print_to_log_and_console(f"No bikes.csv file located.")
                  return None # Nothing to return - no file.
        except:
            # TO DO: RAISE ERROR HERE?
            core_logger.print_to_log_and_console(f"Error attempting to open bikes.csv file.")
            return None # Nothing to return - error parsing file.

        # Endurain gear schema defined in /backend/app/gears/schema.py
        # Relevant functions
             # Existing gear for user: gears.crud: get_gear_user(user_id: int, db: Session) -> list[gears_schema.Gear] | None:
             # Gear lookup by Strava ID: gears.crud: get_gear_by_strava_id_from_user_id(    gear_strava_id: str, user_id: int, db: Session) -> gears_schema.Gear | None:
             # Gear create: gears.crud: create_gear(gear: gears_schema.Gear, user_id: int, db: Session):
             # Gear edit: edit_gear(gear_id: int, gear: gears_schema.Gear, db: Session):
        #print("Getting user gear list") # Testing code
        user_gear_list = gears_crud.get_gear_user(token_user_id, db)
        #print("Gotten user gear list") # Testing code
        #core_logger.print_to_log_and_console(f"User's gear list: {user_gear_list}") # Testing code
        if user_gear_list is None:
             #User has no gear - we can just add our own straight up.
             users_existing_gear_nicknames = None
             core_logger.print_to_log_and_console(f"User has no existing gear.  Adding all Strava bikes.") # Testing code
        else:
             #User has gear - we need to check for duplicates.  Currently checking by nickname.
             core_logger.print_to_log_and_console(f"User has some existing gear. Will only import bikes that are not already present (by checking for nicknames).") # Testing code
             users_existing_gear_nicknames = []
             for item in user_gear_list:
                  #print("Gear item: ", item) # Testing code
                  #print("ID: ", item.id) # Testing code
                  #print("Brand: ", item.brand) # Testing code
                  #print("Model: ", item.model) # Testing code
                  #print("Nickname: ", item.nickname) # Testing code
                  #print("Gear type: ", item.gear_type) # Testing code
                  #print("User: ", item.user_id) # Testing code
                  #print("Created at: ", item.created_at) # Testing code
                  #print("is_active: ", item.is_active) # Testing code
                  #print("strava ID: ", item.strava_gear_id) # Testing code
                  #print("Gear item listing done.") # Testing code
                  users_existing_gear_nicknames.append(item.nickname)
        #print("User existing gear list is: ", users_existing_gear_nicknames) # Testing code
        for bike in bikes_dict:  # bike here is the nickname of the bike from Strava (the index of our bikes_dict)
             core_logger.print_to_log_and_console(f"In bikes_dict iterator.  Current bike is - {bike}") # Testing code.
             #print("In bikes_dict iterator - bike brand is: ", bikes_dict[bike]["Bike Brand"]) # Testing code
             if bike in users_existing_gear_nicknames:
                   core_logger.print_to_log_and_console(f"Bike - {bike} - found in existing user gear (nicknames matched).  Skipping import.")
             else:
                   core_logger.print_to_log_and_console(f"Bike - {bike} - not found in existing user gear. Importing.")
                   # Note - hard-coding gear type of bike to be gear_type of 1 here
                   #    There seems to be no single-point list of gear type in the code.
                   #    Best list appears to be at /frontend/app/src/components/Gears/GearsListComponent.vue
                   # Strava does not export its internal gear ID, so we do not have that information.
                   # Strava does not export the active / inactive state of the bike, so listing all as active (as we need a status).
                   new_gear = gears_schema.Gear(
                         user_id = token_user_id,
                         brand = bikes_dict[bike]["Bike Brand"],
                         model = bikes_dict[bike]["Bike Model"],
                         nickname = bike,
                         gear_type = 1,
                         created_at = import_time_iso,
                         is_active = True,
                         strava_gear_id = None
                        )
                   gears_crud.create_gear(new_gear, token_user_id, db)
                   core_logger.print_to_log_and_console(f"Bike - {bike} - has been imported.")
        # Return a success message
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
