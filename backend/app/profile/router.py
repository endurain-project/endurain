import os
import json

from io import BytesIO
import tempfile
import zipfile

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import users.user.schema as users_schema
import users.user.crud as users_crud
import users.user.utils as users_utils

import users.user_integrations.crud as user_integrations_crud
import users.user_integrations.schema as users_integrations_schema

import users.user_default_gear.crud as user_default_gear_crud
import users.user_default_gear.schema as user_default_gear_schema

import users.user_goals.crud as user_goals_crud
import users.user_goals.schema as user_goals_schema

import users.user_privacy_settings.crud as users_privacy_settings_crud
import users.user_privacy_settings.schema as users_privacy_settings_schema

import profile.utils as profile_utils
import profile.schema as profile_schema

import session.security as session_security
import session.crud as session_crud

import core.database as core_database
import core.config as core_config
import core.logger as core_logger

import activities.activity.crud as activities_crud
import activities.activity.schema as activity_schema

import activities.activity_laps.crud as activity_laps_crud
import activities.activity_laps.schema as activity_laps_schema

import activities.activity_media.crud as activity_media_crud
import activities.activity_media.schema as activity_media_schema

import activities.activity_sets.crud as activity_sets_crud
import activities.activity_sets.schema as activity_sets_schema

import activities.activity_streams.crud as activity_streams_crud
import activities.activity_streams.schema as activity_streams_schema

import activities.activity_workout_steps.crud as activity_workout_steps_crud
import activities.activity_workout_steps.schema as activity_workout_steps_schema

import activities.activity_exercise_titles.crud as activity_exercise_titles_crud
import activities.activity_exercise_titles.schema as activity_exercise_titles_schema

import gears.gear.crud as gear_crud
import gears.gear.schema as gear_schema

import gears.gear_components.crud as gear_components_crud
import gears.gear_components.schema as gear_components_schema

import health_data.crud as health_data_crud
import health_data.schema as health_data_schema

import health_targets.crud as health_targets_crud
import health_targets.schema as health_targets_schema

import websocket.schema as websocket_schema

# Define the API router
router = APIRouter()


@router.get("", response_model=users_schema.UserMe)
async def read_users_me(
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Retrieve the current authenticated user's profile, including integration and privacy settings.

    This endpoint extracts the user ID from the access token, fetches the user from the database,
    and enriches the user object with integration status (Strava, Garmin Connect) and privacy settings.
    Raises HTTP 401 errors if the user, user integrations, or privacy settings are not found.

    Args:
        token_user_id (int): The user ID extracted from the access token.
        db (Session): SQLAlchemy database session dependency.

    Returns:
        User: The user object with additional integration and privacy attributes.

    Raises:
        HTTPException: If the user, user integrations, or privacy settings are not found.
    """
    # Get the user from the database
    user = users_crud.get_user_by_id(token_user_id, db)

    # If the user does not exist raise the exception
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_integrations = user_integrations_crud.get_user_integrations_by_user_id(
        user.id, db
    )

    if user_integrations is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Could not validate credentials (user integrations not found)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user.is_strava_linked = 1 if user_integrations.strava_token else 0
    user.is_garminconnect_linked = 1 if user_integrations.garminconnect_oauth1 else 0

    user_privacy_settings = (
        users_privacy_settings_crud.get_user_privacy_settings_by_user_id(user.id, db)
    )

    if user_privacy_settings is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Could not validate credentials (user privacy settings not found)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    else:
        for attr in vars(user_privacy_settings):
            if not attr.startswith("_") and attr != "id" and attr != "user_id":
                setattr(user, attr, getattr(user_privacy_settings, attr))

    # Return the user
    return user


@router.get("/sessions")
async def read_sessions_me(
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Retrieve all sessions associated with the currently authenticated user.

    Args:
        token_user_id (int): The ID of the user extracted from the access token.
        db (Session): The database session dependency.

    Returns:
        List[Session]: A list of session objects belonging to the authenticated user.
    """
    # Get the sessions from the database
    return session_crud.get_user_sessions(token_user_id, db)


@router.post(
    "/image",
    status_code=201,
    response_model=str | None,
)
async def upload_profile_image(
    file: UploadFile,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Handles the upload of a user's profile image.

    Args:
        file (UploadFile): The image file to be uploaded.
        token_user_id (int): The ID of the user, extracted from the access token.
        db (Session): The database session dependency.

    Returns:
        The result of saving the user's image, as returned by `users_utils.save_user_image`.

    Raises:
        HTTPException: If the upload or save operation fails.
    """
    return await users_utils.save_user_image(token_user_id, file, db)


@router.put("")
async def edit_user(
    user_attributtes: users_schema.User,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Edits the attributes of an existing user in the database.

    Args:
        user_attributtes (users_schema.User): The updated user attributes to be saved.
        token_user_id (int): The ID of the user extracted from the access token.
        db (Session): The database session dependency.

    Returns:
        dict: A dictionary containing a success message with the updated user's ID.
    """
    # Update the user in the database
    users_crud.edit_user(token_user_id, user_attributtes, db)

    # Return success message
    return {"detail": f"User ID {user_attributtes.id} updated successfully"}


@router.put("/privacy")
async def edit_profile_privacy_settings(
    user_privacy_settings: users_privacy_settings_schema.UsersPrivacySettings,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Edits the privacy settings for the currently authenticated user.

    Args:
        user_privacy_settings (users_privacy_settings_schema.UsersPrivacySettings): The new privacy settings to apply to the user.
        token_user_id (int): The ID of the user extracted from the access token.
        db (Session): The database session dependency.

    Returns:
        dict: A message indicating that the user's privacy settings were updated successfully.
    """
    # Edit the user privacy settings in the database
    users_privacy_settings_crud.edit_user_privacy_settings(
        token_user_id, user_privacy_settings, db
    )

    # Return success message
    return {f"User ID {token_user_id} privacy settings updated successfully"}


@router.put("/password")
async def edit_profile_password(
    user_attributtes: users_schema.UserEditPassword,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Asynchronously updates the password for the authenticated user after validating password complexity.

    Args:
        user_attributtes (users_schema.UserEditPassword): The new password data provided by the user.
        token_user_id (int): The ID of the authenticated user, extracted from the access token.
        db (Session): The database session dependency.

    Raises:
        HTTPException: If the new password does not meet complexity requirements.

    Returns:
        dict: A success message indicating the user's password was updated.
    """
    # Check if the password meets the complexity requirements
    is_valid, message = session_security.is_password_complexity_valid(
        user_attributtes.password
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    # Update the user password in the database
    users_crud.edit_user_password(token_user_id, user_attributtes.password, db)

    # Return success message
    return {f"User ID {token_user_id} password updated successfully"}


@router.put("/photo")
async def delete_profile_photo(
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Deletes the profile photo of the authenticated user.

    Args:
        token_user_id (int): The ID of the user obtained from the access token.
        db (Session): The database session dependency.

    Returns:
        str: Success message indicating the user's photo was deleted.
    """
    # Update the user photo_path in the database
    users_crud.delete_user_photo(token_user_id, db)

    # Return success message
    return f"User ID {token_user_id} photo deleted successfully"


@router.delete("/sessions/{session_id}")
async def delete_profile_session(
    session_id: str,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Deletes a user session from the database.

    Args:
        session_id (str): The unique identifier of the session to be deleted.
        token_user_id (int): The ID of the user extracted from the access token.
        db (Session): The database session dependency.

    Returns:
        Any: The result of the session deletion operation, as returned by `session_crud.delete_session`.
    """
    # Delete the session from the database
    return session_crud.delete_session(session_id, token_user_id, db)


# Import/export logic


@router.get("/export")
async def export_profile_data(
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Exports all profile-related data for the authenticated user as a ZIP archive.

    This endpoint collects and packages the user's activities, associated files (such as GPX/FIT tracks), laps, sets, streams, workout steps, exercise titles, gears, health data, health targets, user information, user images, default gear, integrations, goals, and privacy settings into a single ZIP file. The resulting archive contains JSON files for structured data and includes any relevant user or activity files found on disk.

    Args:
        token_user_id (int): The ID of the authenticated user, extracted from the access token.
        db (Session): SQLAlchemy database session dependency.

    Returns:
        StreamingResponse: A streaming response containing the ZIP archive with all exported user data, suitable for download.

    Raises:
        HTTPException: If the user is not found in the database (404 Not Found).
    """

    def sqlalchemy_obj_to_dict(obj):
        """
        Converts a SQLAlchemy model instance into a dictionary mapping column names to their values.

        Args:
            obj: The object to convert. If the object has a __table__ attribute (i.e., is a SQLAlchemy model instance),
                 its columns and corresponding values are extracted into a dictionary. Otherwise, the object is returned as is.

        Returns:
            dict: A dictionary representation of the SQLAlchemy model instance if applicable, otherwise the original object.
        """
        if hasattr(obj, "__table__"):
            return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
        return obj

    def write_json_to_zip(zipf, filename, data, counts, ensure_ascii=False):
        """
        Writes JSON-serialized data to a file within a ZIP archive.

        Args:
            zipf (zipfile.ZipFile): The ZIP file object to write into.
            filename (str): The name of the file to create within the ZIP archive.
            data (Any): The data to serialize as JSON and write to the file.
            ensure_ascii (bool, optional): Whether to escape non-ASCII characters in the output. Defaults to False.

        Notes:
            - If data is falsy (e.g., None, empty), nothing is written.
            - Uses json.dumps with default=str to handle non-serializable objects.
        """
        if data:
            counts[filename.split("/")[-1].replace(".json", "")] = (
                len(data) if isinstance(data, (list, tuple)) else 1
            )
            zipf.writestr(
                filename,
                json.dumps(data, default=str, ensure_ascii=ensure_ascii),
            )

    # Get the user from the database
    user = users_crud.get_user_by_id(token_user_id, db)

    # If the user does not exist raise the exception
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    counts = {
        "media": 0,
        "activity_files": 0,
        "activities": 0,
        "activity_laps": 0,
        "activity_sets": 0,
        "activity_streams": 0,
        "activity_workout_steps": 0,
        "activity_media": 0,
        "activity_exercise_titles": 0,
        "gears": 0,
        "gear_components": 0,
        "health_data": 0,
        "health_targets": 0,
        "user_images": 0,
        "user": 1,
        "user_default_gear": 0,
        "user_integrations": 0,
        "user_goals": 0,
        "user_privacy_settings": 0,
    }

    # Use a temporary file for the ZIP
    def zipfile_generator():
        """
        Generates a ZIP archive containing a user's activities, media files, health data, gear information, and user profile data.

        The ZIP file includes:
            1. Activity track files (GPX/FIT) and associated media files.
            2. Activity metadata (laps, sets, streams, workout steps, exercise titles) in JSON format.
            3. Gear and gear components information in JSON format.
            4. Health data and health targets in JSON format.
            5. User profile information (excluding password) and user images.
            6. User default gear, integrations, goals, and privacy settings in JSON format.
            7. A counts.json file with statistics about the included files.

        The function streams the ZIP file in chunks for efficient memory usage.

        Yields:
            bytes: Chunks of the ZIP file (8192 bytes each).
        """
        with tempfile.NamedTemporaryFile(delete=True) as tmp:
            with zipfile.ZipFile(
                tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
            ) as zipf:
                user_activities = activities_crud.get_user_activities(token_user_id, db)
                laps = []
                sets = []
                streams = []
                steps = []
                exercise_titles = []
                media = []

                # 1) GPX/FIT track files
                if user_activities:
                    # Check if the user has activities files stored and added them to the zip
                    for root, _, files in os.walk(core_config.FILES_PROCESSED_DIR):
                        for file in files:
                            file_id, ext = os.path.splitext(file)
                            if any(
                                str(activity.id) == file_id
                                for activity in user_activities
                            ):
                                counts["activity_files"] += 1
                                file_path = os.path.join(root, file)
                                # Add file to the zip archive under activity_files/ folder
                                arcname = os.path.join(
                                    "activity_files",
                                    os.path.relpath(
                                        file_path, core_config.FILES_PROCESSED_DIR
                                    ),
                                )
                                zipf.write(file_path, arcname)

                    # Check if the user has activity media files stored and added them to the zip
                    for root, _, files in os.walk(core_config.ACTIVITY_MEDIA_DIR):
                        for file in files:
                            file_id, ext = os.path.splitext(file)
                            file_activity_id = file_id.split("_")[0]
                            if any(
                                str(activity.id) == file_activity_id
                                for activity in user_activities
                            ):
                                counts["media"] += 1
                                file_path = os.path.join(root, file)
                                # Add file to the zip archive under activity_media/ folder
                                arcname = os.path.join(
                                    "activity_media",
                                    os.path.relpath(
                                        file_path, core_config.ACTIVITY_MEDIA_DIR
                                    ),
                                )
                                zipf.write(file_path, arcname)

                    # 2) Activities info plus laps, sets, streams, steps, exercise_titles JSON
                    # activities ids
                    activity_ids = [activity.id for activity in user_activities]
                    # laps
                    laps.extend(
                        activity_laps_crud.get_activities_laps(
                            activity_ids, token_user_id, db, user_activities
                        )
                    )
                    # sets
                    sets.extend(
                        activity_sets_crud.get_activities_sets(
                            activity_ids, token_user_id, db, user_activities
                        )
                    )
                    # streams
                    streams.extend(
                        activity_streams_crud.get_activities_streams(
                            activity_ids, token_user_id, db, user_activities
                        )
                    )
                    steps.extend(
                        activity_workout_steps_crud.get_activities_workout_steps(
                            activity_ids, token_user_id, db, user_activities
                        )
                    )
                    media.extend(
                        activity_media_crud.get_activities_media(
                            activity_ids, token_user_id, db, user_activities
                        )
                    )
                # exercise titles
                exercise_titles = (
                    activity_exercise_titles_crud.get_activity_exercise_titles(db)
                )

                # 3) Gears
                gears = gear_crud.get_gear_user(token_user_id, db)

                gear_components = gear_components_crud.get_gear_components_user(
                    token_user_id, db
                )

                # 4) Health data CSV
                health_data = health_data_crud.get_all_health_data_by_user_id(
                    token_user_id, db
                )
                health_targets = health_targets_crud.get_health_targets_by_user_id(
                    token_user_id, db
                )

                # 5) User info JSON
                user_dict = sqlalchemy_obj_to_dict(user)
                user_dict.pop("password", None)
                write_json_to_zip(zipf, "data/user.json", user_dict, counts)

                # Check if the user has user images stored and added them to the zip
                for root, _, files in os.walk(core_config.USER_IMAGES_DIR):
                    for file in files:
                        file_id, ext = os.path.splitext(file)
                        if str(user.id) == file_id:
                            counts["user_images"] += 1
                            file_path = os.path.join(root, file)
                            # Add file to the zip archive under user_images/ folder
                            arcname = os.path.join(
                                "user_images",
                                os.path.relpath(file_path, core_config.USER_IMAGES_DIR),
                            )
                            zipf.write(file_path, arcname)

                user_default_gear = (
                    user_default_gear_crud.get_user_default_gear_by_user_id(
                        token_user_id, db
                    )
                )
                user_integrations = (
                    user_integrations_crud.get_user_integrations_by_user_id(
                        token_user_id, db
                    )
                )
                user_goals = user_goals_crud.get_user_goals_by_user_id(
                    token_user_id, db
                )
                user_privacy_settings = (
                    users_privacy_settings_crud.get_user_privacy_settings_by_user_id(
                        token_user_id, db
                    )
                )

                # Write data to files
                data_to_write = [
                    (user_activities, "data/activities.json"),
                    (laps, "data/activity_laps.json"),
                    (sets, "data/activity_sets.json"),
                    (streams, "data/activity_streams.json"),
                    (steps, "data/activity_workout_steps.json"),
                    (media, "data/activity_media.json"),
                    (exercise_titles, "data/activity_exercise_titles.json"),
                    (gears, "data/gears.json"),
                    (gear_components, "data/gear_components.json"),
                    (health_data, "data/health_data.json"),
                    (health_targets, "data/health_targets.json"),
                    (user_default_gear, "data/user_default_gear.json"),
                    (user_integrations, "data/user_integrations.json"),
                    (user_goals, "data/user_goals.json"),
                    (user_privacy_settings, "data/user_privacy_settings.json"),
                    (counts, "counts.json"),
                ]
                for data, filename in data_to_write:
                    if data:
                        if not isinstance(data, (list, tuple)):
                            data = [data]
                        dicts = [sqlalchemy_obj_to_dict(item) for item in data]
                        write_json_to_zip(zipf, filename, dicts, counts)

            tmp.seek(0)
            while True:
                chunk = tmp.read(8192)
                if not chunk:
                    break
                yield chunk

    headers = {
        "Content-Disposition": f"attachment; filename=user_{token_user_id}_export.zip",
        # Content-Length is omitted for streaming
    }

    try:
        return StreamingResponse(
            zipfile_generator(),
            media_type="application/zip",
            headers=headers,
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in export_profile_data when streaming the response: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


@router.post("/import")
async def import_profile_data(
    file: UploadFile,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    websocket_manager: Annotated[
        websocket_schema.WebSocketManager,
        Depends(websocket_schema.get_websocket_manager),
    ],
):
    """
    Imports user profile data from a provided .zip file, updating or creating user-related records in the database.
    This endpoint expects a .zip file containing JSON and media files representing user profile data, activities, health data, and associated files. It processes and imports the following data types:
    - Gears
    - Gears components
    - User profile
    - User default gear
    - User integrations
    - User goals
    - User privacy settings
    - Activities and their related laps, sets, streams, workout steps, media and exercise titles
    - Health data and health targets
    - User images, activity media and activity files (e.g., .gpx, .fit)
    All imported data is associated with the authenticated user (token_user_id). The function ensures that IDs and user associations are correctly mapped to avoid conflicts. Media files are saved to the appropriate directories.
    Args:
        file (UploadFile): The uploaded .zip file containing the profile data.
        token_user_id (int): The ID of the authenticated user, extracted from the access token.
        db (Session): The database session dependency.
    Returns:
        dict: A summary of the import operation, including counts of imported items.
    Raises:
        HTTPException: If the uploaded file is not a .zip or if any error occurs during import.
    """
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a .zip",
            headers={"WWW-Authenticate": "Bearer"},
        )

    counts = {
        "media": 0,
        "activity_files": 0,
        "activities": 0,
        "activity_laps": 0,
        "activity_sets": 0,
        "activity_streams": 0,
        "activity_workout_steps": 0,
        "activity_media": 0,
        "activity_exercise_titles": 0,
        "gears": 0,
        "gear_components": 0,
        "health_data": 0,
        "health_targets": 0,
        "user_images": 0,
        "user": 0,
        "user_default_gear": 0,
        "user_integrations": 0,
        "user_goals": 0,
        "user_privacy_settings": 0,
    }

    data = await file.read()
    try:
        with zipfile.ZipFile(BytesIO(data)) as zipf:
            file_list = set(zipf.namelist())
            file_map = {
                "data/gears.json": "gears_data",
                "data/gear_components.json": "gear_components_data",
                "data/user.json": "user_data",
                "data/user_default_gear.json": "user_default_gear_data",
                "data/user_integrations.json": "user_integrations_data",
                "data/user_goals.json": "user_goals_data",
                "data/user_privacy_settings.json": "user_privacy_settings_data",
                "data/activities.json": "activities_data",
                "data/activity_laps.json": "activity_laps_data",
                "data/activity_sets.json": "activity_sets_data",
                "data/activity_streams.json": "activity_streams_data",
                "data/activity_workout_steps.json": "activity_workout_steps_data",
                "data/activity_media.json": "activity_media",
                "data/activity_exercise_titles.json": "activity_exercise_titles_data",
                "data/health_data.json": "health_data_data",
                "data/health_targets.json": "health_targets_data",
            }
            results = {}
            gears_id_mapping = {}
            activities_id_mapping = {}

            for filename, varname in file_map.items():
                if filename in file_list:
                    results[varname] = json.loads(zipf.read(filename))
                else:
                    results[varname] = []

            # a) import gears JSON
            if results["gears_data"]:
                for gear_data in results["gears_data"]:
                    # ensure gear has the correct user_id on import
                    gear_data["user_id"] = token_user_id
                    # ensure gear has the correct id on import
                    original_id = gear_data.get("id")
                    gear_data.pop("id", None)
                    # convert gear data to Gear schema
                    gear = gear_schema.Gear(**gear_data)
                    # create gear
                    new_gear = gear_crud.create_gear(gear, token_user_id, db)
                    gears_id_mapping[original_id] = new_gear.id
                    counts["gears"] += 1

            # b) import gear components JSON
            if results["gear_components_data"]:
                for gear_component_data in results["gear_components_data"]:
                    # ensure gear component has the correct user_id and gear_id on import
                    gear_component_data["user_id"] = token_user_id
                    gear_component_data["gear_id"] = (
                        gears_id_mapping.get(gear_component_data["gear_id"])
                        if gear_component_data.get("gear_id") in gears_id_mapping
                        else None
                    )
                    # ensure gear component has the correct id on import
                    original_id = gear_component_data.get("id")
                    gear_component_data.pop("id", None)
                    # convert gear component data to GearComponents schema
                    gear_component = gear_components_schema.GearComponents(
                        **gear_component_data
                    )
                    # create gear component
                    new_gear_component = gear_components_crud.create_gear_component(
                        gear_component, token_user_id, db
                    )
                    gears_id_mapping[original_id] = new_gear_component.id
                    counts["gear_components"] += 1

            # c) import user JSONs
            if results["user_data"]:
                # ensure user has the correct id on import
                results["user_data"]["id"] = token_user_id
                # Split and replace only the filename part
                photo_path = results["user_data"].get("photo_path")
                if isinstance(photo_path, str) and photo_path.startswith(
                    "data/user_images/"
                ):
                    extension = photo_path.split(".")[-1]
                    results["user_data"][
                        "photo_path"
                    ] = f"data/user_images/{token_user_id}.{extension}"
                # convert user data to User schema
                user = users_schema.User(**results["user_data"])
                # Update user
                users_crud.edit_user(token_user_id, user, db)
                counts["user"] += 1

                # user default gear
                if results["user_default_gear_data"]:
                    # current
                    current_user_default_gear = (
                        user_default_gear_crud.get_user_default_gear_by_user_id(
                            token_user_id, db
                        )
                    )
                    results["user_default_gear_data"][0][
                        "id"
                    ] = current_user_default_gear.id
                    # ensure user default gear has the correct user_id on import
                    results["user_default_gear_data"][0]["user_id"] = token_user_id

                    # Map all gear IDs to the new imported gear IDs
                    gear_fields = [
                        "run_gear_id",
                        "trail_run_gear_id",
                        "virtual_run_gear_id",
                        "ride_gear_id",
                        "gravel_ride_gear_id",
                        "mtb_ride_gear_id",
                        "virtual_ride_gear_id",
                        "ows_gear_id",
                        "walk_gear_id",
                        "hike_gear_id",
                        "tennis_gear_id",
                        "alpine_ski_gear_id",
                        "nordic_ski_gear_id",
                        "snowboard_gear_id",
                    ]

                    for field in gear_fields:
                        old_gear_id = results["user_default_gear_data"][0].get(field)
                        if old_gear_id in gears_id_mapping:
                            results["user_default_gear_data"][0][field] = (
                                gears_id_mapping[old_gear_id]
                            )
                        else:
                            results["user_default_gear_data"][0][field] = None

                    # convert user default gear data to UserDefaultGear schema
                    user_default_gear = user_default_gear_schema.UserDefaultGear(
                        **results["user_default_gear_data"][0]
                    )
                    # create or update user default gear
                    user_default_gear_crud.edit_user_default_gear(
                        user_default_gear, token_user_id, db
                    )
                    counts["user_default_gear"] += 1

                # user integrations
                if results["user_integrations_data"]:
                    # current
                    current_user_integrations = (
                        user_integrations_crud.get_user_integrations_by_user_id(
                            token_user_id, db
                        )
                    )
                    results["user_integrations_data"][0][
                        "id"
                    ] = current_user_integrations.id
                    # ensure user integrations has the correct user_id on import
                    results["user_integrations_data"][0]["user_id"] = token_user_id
                    # convert user integrations data to UsersIntegrations schema
                    user_integrations = users_integrations_schema.UsersIntegrations(
                        **results["user_integrations_data"][0]
                    )
                    # create or update user integrations
                    user_integrations_crud.edit_user_integrations(
                        user_integrations, token_user_id, db
                    )
                    counts["user_integrations"] += 1

                # user goals
                if results["user_goals_data"]:
                    for goal_data in results["user_goals_data"]:
                        goal_data.pop("id", None)
                        goal_data.pop("user_id", None)
                        # convert goal data to Goal schema
                        goal = user_goals_schema.UserGoalCreate(**goal_data)
                        # create goal
                        user_goals_crud.create_user_goal(token_user_id, goal, db)
                        counts["user_goals"] += 1

                # user privacy settings
                if results["user_privacy_settings_data"]:
                    # current
                    current_user_privacy_settings = users_privacy_settings_crud.get_user_privacy_settings_by_user_id(
                        token_user_id, db
                    )
                    results["user_privacy_settings_data"][0][
                        "id"
                    ] = current_user_privacy_settings.id
                    # ensure user privacy settings has the correct user_id on import
                    results["user_privacy_settings_data"][0]["user_id"] = token_user_id
                    # convert user integrations data to UsersPrivacySettings schema
                    user_privacy_settings = (
                        users_privacy_settings_schema.UsersPrivacySettings(
                            **results["user_privacy_settings_data"][0]
                        )
                    )
                    # create or update user privacy settings
                    users_privacy_settings_crud.edit_user_privacy_settings(
                        token_user_id, user_privacy_settings, db
                    )
                    counts["user_privacy_settings"] += 1

            # d) import activities JSONs
            for activity_data in results["activities_data"]:
                # ensure activity has the correct user_id and gear_id on import
                activity_data["user_id"] = token_user_id
                activity_data["gear_id"] = (
                    gears_id_mapping.get(activity_data["gear_id"])
                    if activity_data.get("gear_id") in gears_id_mapping
                    else None
                )
                # Remove the id field to avoid conflicts during import
                original_activity_id = activity_data.get("id")
                activity_data.pop("id", None)
                # convert activity data to Activity schema
                activity = activity_schema.Activity(**activity_data)
                # create activity
                new_activity = await activities_crud.create_activity(
                    activity, websocket_manager, db, False
                )
                activities_id_mapping[original_activity_id] = new_activity.id
                counts["activities"] += 1

                # create laps for the activity if available
                if results["activity_laps_data"]:
                    laps = []
                    laps_for_activity = [
                        lap
                        for lap in results["activity_laps_data"]
                        if lap.get("activity_id") == original_activity_id
                    ]
                    for lap_data in laps_for_activity:
                        # Remove the id field to avoid conflicts during import
                        lap_data.pop("id", None)
                        lap_data["activity_id"] = new_activity.id
                        # convert activity data to ActivityLaps schema
                        lap = activity_laps_schema.ActivityLaps(**lap_data)
                        # add the lap to the laps list
                        laps.append(lap_data)
                    activity_laps_crud.create_activity_laps(laps, new_activity.id, db)
                    counts["activity_laps"] += len(laps)

                # create sets for the activity if available
                if results["activity_sets_data"]:
                    sets = []
                    sets_for_activity = [
                        activity_set
                        for activity_set in results["activity_sets_data"]
                        if activity_set.get("activity_id") == original_activity_id
                    ]
                    for activity_set in sets_for_activity:
                        # Remove the id field to avoid conflicts during import
                        activity_set.pop("id", None)
                        activity_set["activity_id"] = new_activity.id
                        # convert activity data to ActivitySets schema
                        set_activity = activity_sets_schema.ActivitySets(**activity_set)
                        # add the set to the sets list
                        sets.append(set_activity)
                    activity_sets_crud.create_activity_sets(sets, new_activity.id, db)
                    counts["activity_sets"] += len(sets)

                # create streams for the activity if available
                if results["activity_streams_data"]:
                    streams = []
                    streams_for_activity = [
                        stream
                        for stream in results["activity_streams_data"]
                        if stream.get("activity_id") == original_activity_id
                    ]
                    for stream_data in streams_for_activity:
                        # Remove the id field to avoid conflicts during import
                        stream_data.pop("id", None)
                        stream_data["activity_id"] = new_activity.id
                        # convert activity data to ActivityStreams schema
                        stream = activity_streams_schema.ActivityStreams(**stream_data)
                        # add the stream to the streams list
                        streams.append(stream)
                    activity_streams_crud.create_activity_streams(streams, db)
                    counts["activity_streams"] += len(streams)

                # create workout steps for the activity if available
                if results["activity_workout_steps_data"]:
                    steps = []
                    steps_for_activity = [
                        step
                        for step in results["activity_workout_steps_data"]
                        if step.get("activity_id") == original_activity_id
                    ]
                    for step_data in steps_for_activity:
                        # Remove the id field to avoid conflicts during import
                        step_data.pop("id", None)
                        step_data["activity_id"] = new_activity.id
                        # convert activity data to ActivityWorkoutSteps schema
                        step = activity_workout_steps_schema.ActivityWorkoutSteps(
                            **step_data
                        )
                        # add the step to the steps list
                        steps.append(step)
                    activity_workout_steps_crud.create_activity_workout_steps(
                        steps, new_activity.id, db
                    )
                    counts["activity_workout_steps"] += len(steps)

                # create media for the activity if available
                if results["activity_media"]:
                    media = []
                    media_for_activity = [
                        media_item
                        for media_item in results["activity_media"]
                        if media_item.get("activity_id") == original_activity_id
                    ]
                    for media_data in media_for_activity:
                        # Remove the id field to avoid conflicts during import
                        media_data.pop("id", None)
                        media_data["activity_id"] = new_activity.id
                        # Update the media_path
                        old_path = media_data.get("media_path", None)
                        if old_path:
                            # Extract the part after the underscore
                            filename = old_path.split("/")[-1]
                            suffix = filename.split("_", 1)[1]
                            media_data["media_path"] = (
                                f"{core_config.ACTIVITY_MEDIA_DIR}/{new_activity.id}_{suffix}"
                            )
                        # convert activity data to ActivityMedia schema
                        media_item = activity_media_schema.ActivityMedia(**media_data)
                        # add the media item to the media list
                        media.append(media_item)
                    activity_media_crud.create_activity_medias(
                        media, new_activity.id, db
                    )
                    counts["activity_media"] += len(media)

                # create exercise titles for the activity if available
                if results["activity_exercise_titles_data"]:
                    titles = []
                    exercise_titles_for_activity = [
                        title
                        for title in results["activity_exercise_titles_data"]
                        if title.get("activity_id") == original_activity_id
                    ]
                    for title_data in exercise_titles_for_activity:
                        # Remove the id field to avoid conflicts during import
                        title_data.pop("id", None)
                        title_data["activity_id"] = new_activity.id
                        # convert activity data to ActivityExerciseTitles schema
                        title = activity_exercise_titles_schema.ActivityExerciseTitles(
                            **title_data
                        )
                        # add the title to the titles list
                        titles.append(title)
                    activity_exercise_titles_crud.create_activity_exercise_titles(
                        titles, db
                    )
                    counts["activity_exercise_titles"] += len(titles)

            # e) import health CSV
            if results["health_data_data"]:
                # ensure health data has the correct user_id on import
                for health_data in results["health_data_data"]:
                    health_data["user_id"] = token_user_id
                    # Remove the id field to avoid conflicts during import
                    health_data.pop("id", None)
                    # convert activity data to ActivityLaps schema
                    data = health_data_schema.HealthData(**health_data)
                    # create health data
                    health_data_crud.create_health_data(token_user_id, data, db)
                    counts["health_data"] += 1

            # f) import health targets JSON
            if results["health_targets_data"]:
                # ensure health targets has the correct user_id on import
                for target_data in results["health_targets_data"]:
                    # current
                    current_health_target = (
                        health_targets_crud.get_health_targets_by_user_id(
                            token_user_id, db
                        )
                    )
                    # ensure health target has the correct user_id
                    target_data["user_id"] = token_user_id
                    # Remove the id field to avoid conflicts during import
                    target_data["id"] = current_health_target.id
                    # convert activity data to ActivityLaps schema
                    target = health_targets_schema.HealthTargets(**target_data)
                    # create health target
                    health_targets_crud.edit_health_target(target, token_user_id, db)
                    counts["health_targets"] += 1

            # g) import user images and activity files if available to disk
            for file_l in file_list:
                path = file_l.replace("\\", "/")

                # import user image if available
                if path.lower().endswith((".png", ".jpg", ".jpeg")) and path.startswith(
                    "user_images/"
                ):
                    # Check if the user image is for the current user
                    ext = os.path.splitext(path)[1]
                    new_file_name = f"{token_user_id}{ext}"
                    user_img = os.path.join(core_config.USER_IMAGES_DIR, new_file_name)
                    with open(user_img, "wb") as f:
                        f.write(zipf.read(file_l))
                    counts["user_images"] += 1
                # import activity files if available
                elif path.lower().endswith(
                    (".gpx", ".fit", ".tcx")
                ) and path.startswith("activity_files/"):
                    file_id = os.path.splitext(os.path.basename(path))[0]
                    ext = os.path.splitext(path)[1]
                    new_id = activities_id_mapping.get(file_id)

                    if new_id is None:
                        continue

                    new_file_name = f"{new_id}{ext}"
                    activity_file_path = os.path.join(
                        core_config.FILES_PROCESSED_DIR, new_file_name
                    )
                    with open(activity_file_path, "wb") as f:
                        f.write(zipf.read(file_l))
                    counts["activity_files"] += 1
                # import activity media if available
                elif path.lower().endswith(
                    (".png", ".jpg", ".jpeg")
                ) and path.startswith("activity_media/"):
                    # Extract the original filename and split into ID and suffix
                    file_name = os.path.basename(path)  # e.g. "1098_thumbnail.png"
                    base_name, ext = os.path.splitext(
                        file_name
                    )  # base_name="1098_thumbnail", ext=".png"
                    orig_id, suffix = base_name.split(
                        "_", 1
                    )  # orig_id="1098", suffix="thumbnail"
                    # Look up the new activity ID
                    new_id = activities_id_mapping.get(orig_id)
                    if new_id is None:
                        # no mapping for this activity → skip
                        continue
                    # Build the new filename and full path
                    new_file_name = (
                        f"{new_id}_{suffix}{ext}"  # e.g. "4321_thumbnail.png"
                    )
                    activity_media_path = os.path.join(
                        core_config.ACTIVITY_MEDIA_DIR, new_file_name
                    )
                    # Extract & write out
                    with open(activity_media_path, "wb") as f:
                        f.write(zipf.read(file_l))
                    # Increment your counter
                    counts["media"] += 1

        return {"detail": "Import completed", "imported": counts}
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        core_logger.print_to_log(
            f"Error in import_profile_data: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Import failed: {err}",
        ) from err


# MFA logic
@router.get("/mfa/status", response_model=profile_schema.MFAStatusResponse)
async def get_mfa_status(
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """
    Return the multi-factor authentication (MFA) enabled status for the authenticated user.

    This async route handler expects the authenticated user's ID to be injected from an access
    token and a database session to be provided via dependency injection. It checks whether the
    user has MFA enabled by delegating to profile_utils.is_mfa_enabled_for_user and returns the
    result wrapped in the profile_schema.MFAStatusResponse model.

    Args:
        token_user_id (int): User ID extracted from the access token (provided by
            session_security.get_user_id_from_access_token dependency).
        db (Session): SQLAlchemy database session (provided by core_database.get_db dependency).

    Returns:
        profile_schema.MFAStatusResponse: Response object with a single attribute:
            - mfa_enabled (bool): True if the user has MFA enabled, False otherwise.

    Raises:
        HTTPException: If authentication fails or the access token is invalid (raised by the
            dependency that extracts the user ID).
        sqlalchemy.exc.SQLAlchemyError: On database-related errors originating from the DB session
            or helper functions.

    Notes:
        - This function performs a read-only check and does not modify persistent state.
        - Intended to be used as a FastAPI route handler; the dependencies supply authentication
          and the DB session automatically.
        - Example serialized response: {"mfa_enabled": true}
    """
    is_enabled = profile_utils.is_mfa_enabled_for_user(token_user_id, db)
    return profile_schema.MFAStatusResponse(mfa_enabled=is_enabled)


@router.post("/mfa/setup", response_model=profile_schema.MFASetupResponse)
async def setup_mfa(
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    mfa_secret_store: Annotated[
        profile_schema.MFASecretStore, Depends(profile_schema.get_mfa_secret_store)
    ],
):
    """
    Initiate MFA setup for the authenticated user.

    Generates a new TOTP secret and associated provisioning data for the user identified
    by token_user_id, persists any required MFA metadata using the provided database
    session, and temporarily stores the raw secret in mfa_secret_store for the
    subsequent enable/verification step.

    Args:
        token_user_id (int): User ID extracted from the access token via
            session_security.get_user_id_from_access_token. The MFA setup will be
            performed for this user.
        db (Session): Database session (injected via core_database.get_db) used by
            profile_utils.setup_user_mfa to persist user MFA metadata.
        mfa_secret_store (profile_schema.MFASecretStore): Ephemeral secret store (injected
            via profile_schema.get_mfa_secret_store). The generated raw secret is added
            with mfa_secret_store.add_secret(token_user_id, secret) so it can be
            verified in a subsequent request that enables MFA.

    Returns:
        object: The response returned by profile_utils.setup_user_mfa. Typically this
        contains the information needed by the client to configure an authenticator
        app (for example: secret or masked secret, otpauth URI, and/or QR code data).

    Side effects:
        - Persists MFA-related metadata in the database via profile_utils.setup_user_mfa.
        - Temporarily stores the raw TOTP secret in mfa_secret_store; callers should
          ensure secrets are removed or expired after successful verification to avoid
          long-lived plaintext secrets.

    Errors/Exceptions:
        - Authentication/authorization errors if the access token is invalid or does not
          resolve to a user id (raised by the dependency).
        - Database-related errors from profile_utils.setup_user_mfa or the db session.
        - Storage errors from mfa_secret_store.add_secret (e.g., failure to persist the secret).
        Callers (API layer) should translate these into appropriate HTTP responses.

    Notes:
        - Intended to be used as a FastAPI endpoint where token_user_id and db are
          provided via Depends().
        - Ensure mfa_secret_store implements appropriate concurrency control and TTL/expiry
          for stored secrets.
    """
    response = profile_utils.setup_user_mfa(token_user_id, db)

    # Store the secret temporarily for the enable step
    mfa_secret_store.add_secret(token_user_id, response.secret)

    return response


@router.post("/mfa/enable")
async def enable_mfa(
    request: profile_schema.MFASetupRequest,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    mfa_secret_store: Annotated[
        profile_schema.MFASecretStore, Depends(profile_schema.get_mfa_secret_store)
    ],
):
    """
    Enable Multi-Factor Authentication (MFA) for the authenticated user.

    Completes an in-progress MFA setup by retrieving the temporary secret for the user,
    validating the provided one-time code (TOTP) and persisting the MFA configuration.
    The temporary secret is removed from the store on success or error to avoid leaking secrets.

    Parameters
    ----------
    request : profile_schema.MFASetupRequest
        Request body containing the MFA code (TOTP) submitted by the user.
    token_user_id : int
        ID of the authenticated user, injected from the access token dependency.
    db : Session
        Database session used to persist the user's MFA settings.
    mfa_secret_store : profile_schema.MFASecretStore
        Temporary storage used to retrieve and delete the user's MFA secret during setup.

    Returns
    -------
    dict
        JSON-serializable success message: {"message": "MFA enabled successfully"}.

    Raises
    ------
    HTTPException
        - 400 Bad Request if there is no MFA setup in progress (no temporary secret available).
        - Propagates HTTPException raised by the underlying validation/persistence (e.g., invalid TOTP,
          database errors). On any error the temporary secret is removed to ensure cleanup.

    Side effects
    ------------
    - Calls profile_utils.enable_user_mfa(...) to validate and enable MFA for the user.
    - Deletes the temporary MFA secret from mfa_secret_store in both success and error paths.
    """
    # Get the secret from temporary storage
    secret = mfa_secret_store.get_secret(token_user_id)
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No MFA setup in progress. Please run setup first.",
        )

    try:
        profile_utils.enable_user_mfa(token_user_id, secret, request.mfa_code, db)
        # Clean up the temporary secret
        mfa_secret_store.delete_secret(token_user_id)
        return {"message": "MFA enabled successfully"}
    except HTTPException:
        # Clean up on error
        mfa_secret_store.delete_secret(token_user_id)
        raise


@router.post("/mfa/disable")
async def disable_mfa(
    request: profile_schema.MFADisableRequest,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """Disable multi-factor authentication (MFA) for the authenticated user.

    Asynchronous FastAPI route handler that disables MFA for the user identified by
    the access token. It validates the MFA code provided in the request and delegates
    the disabling operation to profile_utils.disable_user_mfa, persisting the change
    using the supplied database session.

    Args:
        request (profile_schema.MFADisableRequest): Request payload containing the MFA code
            (expected attribute: `mfa_code`).
        token_user_id (int): ID of the authenticated user, resolved from the access token
            via dependency injection.
        db (Session): SQLAlchemy database session provided by dependency injection.

    Returns:
        dict: A JSON-serializable dict with a success message, e.g.:
            {"message": "MFA disabled successfully"}

    Raises:
        fastapi.HTTPException: If authentication fails or required dependencies cannot be resolved.
        ValueError: If the provided MFA code is invalid (actual exception type may vary
            depending on profile_utils implementation).
        sqlalchemy.exc.SQLAlchemyError: If a database error occurs while updating the user's record.
        Exception: Propagates other unexpected errors thrown by profile_utils.disable_user_mfa.

    Notes:
        - This function relies on FastAPI's Depends to supply token_user_id and db.
        - Side effects: updates the user's MFA state in the database.
    """
    profile_utils.disable_user_mfa(token_user_id, request.mfa_code, db)
    return {"message": "MFA disabled successfully"}


@router.post("/mfa/verify")
async def verify_mfa(
    request: profile_schema.MFARequest,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    is_valid = profile_utils.verify_user_mfa(token_user_id, request.mfa_code, db)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid MFA code"
        )
    return {"message": "MFA code verified successfully"}
