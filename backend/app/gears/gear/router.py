from typing import Annotated, Callable

from fastapi import APIRouter, Depends, HTTPException, status, Security
from sqlalchemy.orm import Session

import session.security as session_security

import gears.gear.schema as gears_schema
import gears.gear.crud as gears_crud
import gears.gear.dependencies as gears_dependencies

import core.database as core_database

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
        core_logger.print_to_log("Entering shoe importing function.")

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
                  core_logger.print_to_log_and_console(f"Strava {shoesfilename} file parsed and gear dictionary created. File was {len(shoes_list)} rows long, ignoring header row.")
            else:
                  core_logger.print_to_log_and_console(f"No {shoesfilename} file located in the {bulk_import_dir} directory.")
                  return None # Nothing to return - no file.

        except Exception as err:
            # TO DO: RAISE ERROR OR ADD NOTIFICATION HERE?
            core_logger.print_to_log_and_console(f"Error attempting to open {shoes_file_path} file:  {err}", "error")
            return None # Nothing to return - error parsing file.

        # Get user's existing gear 
        user_gear_list = gears_crud.get_gear_user(token_user_id, db)
        # Saving DB calls by doing this once for the entire gear import
        #   But one issue with pulling the DB before the import loop below: if a user's import has duplicate gear nicknames in it, this will not be caught by this check.
        #   But calling the get_gear_user function during the for loop below results in an error, and also would be tons of db calls for large gear imports.
        #   So, adding a duplicate-nickname check within a single import run to handle this case.

        # Create list of nicknames, to build new names for un-named shoes and to check for overlapping nicknames during this import
        user_gear_nicknames = []
        if user_gear_list is not None:
             for item in user_gear_list:
                   user_gear_nicknames.append(item.nickname.lower())

        # Get gear type id of shoes
        shoe_gear_type = gears_utils.GEAR_NAME_TO_ID["shoes"]

        # Go through shoes and add them to the database if they are not duplicates.
        for shoerow in shoes_list:  
             # Strava allows nameless shoes, but Endurain does not.  Check for nameless shoes and add a novel name.
             blank_name = False
             if shoerow["Shoe Name"] == None or shoerow["Shoe Name"] == "" or shoerow["Shoe Name"].replace("+", " ").strip() == "":
                   blank_name = True
                   duplicate_name = True
                   newnumber=1
                   while duplicate_name:
                         proposed_name = core_config.STRAVA_BULK_IMPORT_SHOES_UNNAMED_SHOE + str(newnumber)
                         if proposed_name.lower() in user_gear_nicknames:
                               newnumber+=1
                         else:
                               duplicate_name = False

             # Use new name, if we have one.
             if blank_name:
                   shoe_name = proposed_name
                   core_logger.print_to_log_and_console(f"Shoe name was blank, it has been updated to: {proposed_name}")
             else:
                   shoe_name = shoerow["Shoe Name"]

             # Check for duplicate gear already present, and abort import of this item if name overlaps
             #   Note - shoes that have a blank name in Strava and that have already been imported once will NOT be detected as duplicates, as the name will have been changed from the (blank) Strava name.
             shoerowalreadypresent = False
             gear_item_dict = {"name": shoe_name, "brand": shoerow["Shoe Brand"], "model": shoerow["Shoe Model"], "gear_type": shoe_gear_type}
             name_duplicated, gear_duplicated, duplicate_item = gears_utils.is_gear_duplicate(gear_item_dict, user_gear_list)     # checks for duplicate existing in database before this import round
             if shoe_name.replace("+", " ").lower() in user_gear_nicknames: name_duplicated = True                                # checks for duplicate during this import round
             if name_duplicated:
                   # At least the nickname is duplicated, so do not import.  The following logic explains various cases to the user.
                   if gear_duplicated:
                         if duplicate_item.strava_gear_id is None:
                               core_logger.print_to_log_and_console(f"Shoe - {shoe_name} - found in existing user gear.  Skipping import.")
                         else:
                               core_logger.print_to_log_and_console(f"Shoe - {shoe_name} - was found in existing user gear, linked to Strava.  Skipping import, but be aware that the shoe will be removed if Strava is unlinked.")
                   else:
                         core_logger.print_to_log_and_console(f"Shoe - {shoe_name} - nickname of shoe was found in existing user gear.  Skipping import, as nicknames cannot overlap (capitalization does not matter).")
             else:
                   core_logger.print_to_log_and_console(f"Shoe - {shoe_name} - not found in existing user gear. Importing. Strava data on the shoe is: {shoerow}")
                   # Notes on the import:
                   # Strava does not export its internal gear ID, so we do not have that information.
                   # Strava does not export the active / inactive state of the shoe, so importing all as active (as we need a status).
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
                   added_gear = gears_crud.create_gear(new_gear, token_user_id, db)
                   core_logger.print_to_log_and_console(f"Shoe - {shoe_name} - has been imported.")
                   user_gear_nicknames.append(added_gear.nickname.lower()) # for checking of duplicated names during a single import, case-insenitively

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
