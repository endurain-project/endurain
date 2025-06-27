import os
import json

from io import BytesIO
import zipfile

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import gears.schema as gear_schema

import users.user.schema as users_schema
import users.user.crud as users_crud
import users.user.utils as users_utils

import users.user_integrations.crud as user_integrations_crud
import users.user_integrations.schema as users_integrations_schema

import users.user_default_gear.crud as user_default_gear_crud
import users.user_default_gear.schema as user_default_gear_schema

import users.user_privacy_settings.crud as users_privacy_settings_crud
import users.user_privacy_settings.schema as users_privacy_settings_schema

import session.security as session_security
import session.crud as session_crud

import core.database as core_database
import core.config as core_config
import core.logger as core_logger

import activities.activity.crud as activities_crud

import activities.activity_laps.crud as activity_laps_crud

import activities.activity_sets.crud as activity_sets_crud

import activities.activity_streams.crud as activity_streams_crud

import activities.activity_workout_steps.crud as activity_workout_steps_crud

import activities.activity_exercise_titles.crud as activity_exercise_titles_crud

import gears.crud as gear_crud

import health_data.crud as health_crud

import health_targets.crud as health_targets_crud

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
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_integrations = user_integrations_crud.get_user_integrations_by_user_id(
        user.id, db
    )

    if user_integrations is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
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
            status_code=status.HTTP_401_UNAUTHORIZED,
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

    This endpoint collects and packages the user's activities, associated files (such as GPX/FIT tracks), laps, sets, streams, workout steps, exercise titles, gears, health data, health targets, user information, user images, default gear, integrations, and privacy settings into a single ZIP file. The resulting archive contains JSON files for structured data and includes any relevant user or activity files found on disk.

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
            obj: The object to convert. If the object has a `__table__` attribute (i.e., is a SQLAlchemy model instance),
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
            - If `data` is falsy (e.g., None, empty), nothing is written.
            - Uses `json.dumps` with `default=str` to handle non-serializable objects.
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

    buf = BytesIO()
    with zipfile.ZipFile(
        buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as zipf:
        counts = {
            "activity_files": 0,
            "activities": 0,
            "activity_laps": 0,
            "activity_sets": 0,
            "activity_streams": 0,
            "activity_workout_steps": 0,
            "activity_exercise_titles": 0,
            "gears": 0,
            "health_data": 0,
            "health_targets": 0,
            "user_images": 0,
            "user": 1,
            "user_default_gear": 0,
            "user_integrations": 0,
            "user_privacy_settings": 0,
        }
        user_activities = activities_crud.get_user_activities(token_user_id, db)
        laps = []
        sets = []
        streams = []
        steps = []
        exercise_titles = []

        # 1) GPX/FIT track files
        if user_activities:
            # Check if the user has activities files stored and added them to the zip
            for root, _, files in os.walk(core_config.FILES_PROCESSED_DIR):
                for file in files:
                    file_id, ext = os.path.splitext(file)
                    print(
                        f"Processing file: {file} with ID: {file_id} and extension: {ext}"
                    )
                    if any(str(activity.id) == file_id for activity in user_activities):
                        print(f"Adding file: {file} to zip")
                        counts["activity_files"] += 1
                        file_path = os.path.join(root, file)
                        # Add file to the zip archive with relative path
                        arcname = os.path.relpath(
                            file_path, core_config.FILES_PROCESSED_DIR
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
            # steps
            steps.extend(
                activity_workout_steps_crud.get_activities_workout_steps(
                    activity_ids, token_user_id, db, user_activities
                )
            )
            # exercise titles
            exercise_titles = (
                activity_exercise_titles_crud.get_activity_exercise_titles(db)
            )

        # 3) Gears
        gears = gear_crud.get_gear_user(token_user_id, db)

        # 4) Health data CSV
        health_data = health_crud.get_all_health_data_by_user_id(token_user_id, db)
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
                print(
                    f"Processing file: {file} with ID: {file_id} and extension: {ext}"
                )
                if str(user.id) == file_id:
                    print(f"Adding user image: {file} to zip")
                    counts["user_images"] += 1
                    file_path = os.path.join(root, file)
                    # Add user image to the zip archive with relative path
                    arcname = os.path.relpath(file_path, core_config.USER_IMAGES_DIR)
                    zipf.write(file_path, arcname)

        user_default_gear = user_default_gear_crud.get_user_default_gear_by_user_id(
            token_user_id, db
        )
        user_integrations = user_integrations_crud.get_user_integrations_by_user_id(
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
            (exercise_titles, "data/activity_exercise_titles.json"),
            (gears, "data/gears.json"),
            (health_data, "data/health_data.json"),
            (health_targets, "data/health_targets.json"),
            (user_default_gear, "data/user_default_gear.json"),
            (user_integrations, "data/user_integrations.json"),
            (user_privacy_settings, "data/user_privacy_settings.json"),
            (counts, "counts.json"),
        ]
        for data, filename in data_to_write:
            if data:
                if not isinstance(data, (list, tuple)):
                    data = [data]
                dicts = [sqlalchemy_obj_to_dict(item) for item in data]
                write_json_to_zip(zipf, filename, dicts, counts)

    buf.seek(0)
    headers = {
        "Content-Disposition": f"attachment; filename=user_{token_user_id}_export.zip",
        "Content-Length": str(len(buf.getvalue())),
    }
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers=headers,
    )


@router.post("/import")
async def import_profile_data(
    file: UploadFile,
    token_user_id: int = Depends(session_security.get_user_id_from_access_token),
    db: Session = Depends(core_database.get_db),
):
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a .zip",
            headers={"WWW-Authenticate": "Bearer"},
        )

    counts = {
        "activity_files": 0,
        "activities": 0,
        "activity_laps": 0,
        "activity_sets": 0,
        "activity_streams": 0,
        "activity_workout_steps": 0,
        "activity_exercise_titles": 0,
        "gears": 0,
        "health_data": 0,
        "health_targets": 0,
        "user_images": 0,
        "user": 0,
        "user_default_gear": 0,
        "user_integrations": 0,
        "user_privacy_settings": 0,
    }

    data = await file.read()
    try:
        with zipfile.ZipFile(BytesIO(data)) as zipf:
            file_list = set(zipf.namelist())
            file_map = {
                "data/gears.json": "gears_data",
                "data/user.json": "user_data",
                "data/user_default_gear.json": "user_default_gear_data",
                "data/user_integrations.json": "user_integrations_data",
                "data/user_privacy_settings.json": "user_privacy_settings_data",
                "data/activities.json": "activities_data",
                "data/activity_laps.json": "activity_laps_data",
                "data/activity_sets.json": "activity_sets_data",
                "data/activity_streams.json": "activity_streams_data",
                "data/activity_workout_steps.json": "activity_workout_steps_data",
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

            # b) import user JSONs
            if results["user_data"]:
                # ensure user has the correct id on import
                results["user_data"]["id"] = token_user_id
                # Split and replace only the filename part
                photo_path = results["user_data"].get("photo_path")
                if isinstance(photo_path, str) and photo_path.startswith(
                    "user_images/"
                ):
                    extension = photo_path.split(".")[-1]
                    results["user_data"][
                        "photo_path"
                    ] = f"user_images/{token_user_id}.{extension}"
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
                    # convert user integrations data to UsersIntegrations schema
                    user_privacy_settings = users_integrations_schema.UsersIntegrations(
                        **results["user_privacy_settings_data"][0]
                    )
                    # create or update user privacy settings
                    users_privacy_settings_crud.edit_user_privacy_settings(
                        token_user_id, user_privacy_settings, db
                    )
                    counts["user_privacy_settings"] += 1

            # c) import activities JSONs
            for activity in results["activities_data"]:
                # ensure activity has the correct user_id on import
                activity["user_id"] = token_user_id
                activity["gear_id"] = (
                    gears_id_mapping.get(activity["gear_id"])
                    if activity.get("gear_id") in gears_id_mapping
                    else None
                )
                # Remove the id field to avoid conflicts during import
                activity.pop("id", None)
                # create activity
                new_activity = activities_crud.create_activity(activity, db)
                activities_id_mapping[activity["id"]] = new_activity.id
                counts["activities"] += 1

                # create laps for the activity if available
                if results["activity_laps_data"]:
                    laps_for_activity = [
                        lap
                        for lap in results["activity_laps_data"]
                        if lap.get("activity_id") == activity["id"]
                    ]
                    for lap in laps_for_activity:
                        # Remove the id field to avoid conflicts during import
                        lap.pop("id", None)
                        lap["activity_id"] = new_activity.id
                    activity_laps_crud.create_activity_laps(laps_for_activity, db)
                    counts["activity_laps"] += 1

                # create sets for the activity if available
                if results["activity_sets_data"]:
                    sets_for_activity = [
                        activity_set
                        for activity_set in results["activity_sets_data"]
                        if activity_set.get("activity_id") == activity["id"]
                    ]
                    for activity_set in sets_for_activity:
                        # Remove the id field to avoid conflicts during import
                        activity_set.pop("id", None)
                        activity_set["activity_id"] = new_activity.id
                    activity_sets_crud.create_activity_sets(sets_for_activity, db)
                    counts["activity_sets"] += 1

                # create streams for the activity if available
                if results["activity_streams_data"]:
                    streams_for_activity = [
                        stream
                        for stream in results["activity_streams_data"]
                        if stream.get("activity_id") == activity["id"]
                    ]
                    for stream in streams_for_activity:
                        # Remove the id field to avoid conflicts during import
                        stream.pop("id", None)
                        stream["activity_id"] = new_activity.id
                    activity_streams_crud.create_activity_streams(
                        streams_for_activity, db
                    )
                    counts["activity_streams"] += 1

                # create workout steps for the activity if available
                if results["activity_workout_steps_data"]:
                    steps_for_activity = [
                        step
                        for step in results["activity_workout_steps_data"]
                        if step.get("activity_id") == activity["id"]
                    ]
                    for step in steps_for_activity:
                        # Remove the id field to avoid conflicts during import
                        step.pop("id", None)
                        step["activity_id"] = new_activity.id
                    activity_workout_steps_crud.create_activity_workout_steps(
                        steps_for_activity, db
                    )
                    counts["activity_workout_steps"] += 1

                # create exercise titles for the activity if available
                if results["activity_exercise_titles_data"]:
                    exercise_titles_for_activity = [
                        title
                        for title in results["activity_exercise_titles_data"]
                        if title.get("activity_id") == activity["id"]
                    ]
                    for title in exercise_titles_for_activity:
                        # Remove the id field to avoid conflicts during import
                        title.pop("id", None)
                        title["activity_id"] = new_activity.id
                    activity_exercise_titles_crud.create_activity_exercise_titles(
                        exercise_titles_for_activity, db
                    )
                    counts["activity_exercise_titles"] += 1

            # d) import health CSV
            if results["health_data_data"]:
                # ensure health data has the correct user_id on import
                for data in results["health_data_data"]:
                    data["user_id"] = token_user_id
                    # Remove the id field to avoid conflicts during import
                    data.pop("id", None)
                    # create health data
                    health_crud.create_health_data(data, db)
                    counts["health_data"] += 1

            # e) import health targets JSON
            if results["health_targets_data"]:
                # ensure health targets has the correct user_id on import
                for target in results["health_targets_data"]:
                    target["user_id"] = token_user_id
                    # Remove the id field to avoid conflicts during import
                    target.pop("id", None)
                    # create health target
                    health_targets_crud.edit_health_target(target, token_user_id, db)
                    counts["health_targets"] += 1

            # f) import user images and activity files if available to disk
            for file in file_list:
                path = file.replace("\\", "/")

                if path.lower().endswith((".png", ".jpg", ".jpeg")):
                    ext = os.path.splitext(path)[1]
                    new_file_name = f"{token_user_id}{ext}"
                    user_img = os.path.join(core_config.USER_IMAGES_DIR, new_file_name)
                    with open(user_img, "wb") as f:
                        f.write(zipf.read(file))
                    counts["user_images"] += 1

                elif path.lower().endswith((".gpx", ".fit")):
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
                        f.write(zipf.read(file))
                    counts["activity_files"] += 1

            """ for entry in zipf.namelist():
                path = entry.replace("\\", "/")

                # a) import user image if available to disk
                if path.lower().endswith((".png", ".jpg", ".jpeg")):
                    file_id, ext = os.path.splitext(path)
                    new_file_name = f"{token_user_id}.{ext.lstrip('.')}"
                    user_img = os.path.join(core_config.USER_IMAGES_DIR, new_file_name)
                    with open(user_img, "wb") as user_images_folder:
                        user_images_folder.write(zipf.read(entry))
                    counts["user_images"] += 1

                # b) import gears JSON
                elif path == "data/gears.json":
                    gears_data = json.loads(zipf.read(entry))
                    for gear_data in gears_data:
                        # ensure gear has the correct user_id on import
                        gear_data["user_id"] = token_user_id
                        gear_data[0].pop("id", None)
                        # convert gear data to Gear schema
                        gear = gear_schema.Gear(
                            **gear_data
                        )
                        # create gear
                        new_gear = gear_crud.create_gear(gear, db)
                        gears_id_mapping[gear["id"]] = new_gear.id
                        counts["gears"] += 1

                # c) import user JSON
                elif path == "data/user.json":
                    user_data = json.loads(zipf.read(entry))
                    # ensure user has the correct id on import
                    user_data["id"] = token_user_id
                    # convert user data to User schema
                    user = users_schema.User(**user_data)
                    # Update user
                    users_crud.edit_user(token_user_id, user, db)
                    counts["user"] += 1
                    # user default gear
                    user_default_gear_data = json.loads(
                        zipf.read("data/user_default_gear.json")
                    )
                    if user_default_gear_data:
                        # ensure user default gear has the correct user_id on import
                        user_default_gear_data[0]["user_id"] = token_user_id
                        # Remove the id field to avoid conflicts during import
                        user_default_gear_data[0].pop("id", None)
                        # convert user default gear data to UserDefaultGear schema
                        user_default_gear = user_default_gear_schema.UserDefaultGear(
                            **user_default_gear_data[0]
                        )
                        # create or update user default gear
                        user_default_gear_crud.edit_user_default_gear(
                            user_default_gear, token_user_id, db
                        )
                        counts["user_default_gear"] += 1
                    # user integrations
                    user_integrations_data = json.loads(
                        zipf.read("data/user_integrations.json")
                    )
                    if user_integrations_data:
                        # ensure user integrations has the correct user_id on import
                        user_integrations_data[0]["user_id"] = token_user_id
                        # Remove the id field to avoid conflicts during import
                        user_integrations_data[0].pop("id", None)
                        # convert user integrations data to UsersIntegrations schema
                        user_integrations = users_integrations_schema.UsersIntegrations(
                            **user_integrations_data[0]
                        )
                        # create or update user integrations
                        user_integrations_crud.edit_user_integrations(
                            user_integrations, token_user_id, db
                        )
                        counts["user_integrations"] += 1
                    # user privacy settings
                    user_privacy_settings_data = json.loads(
                        zipf.read("data/user_privacy_settings.json")
                    )
                    if user_privacy_settings_data:
                        # ensure user privacy settings has the correct user_id on import
                        user_privacy_settings_data[0]["user_id"] = token_user_id
                        # Remove the id field to avoid conflicts during import
                        user_privacy_settings_data[0].pop("id", None)
                        # convert user integrations data to UsersIntegrations schema
                        user_privacy_settings = users_integrations_schema.UsersIntegrations(
                            **user_privacy_settings_data[0]
                        )
                        # create or update user privacy settings
                        users_privacy_settings_crud.edit_user_privacy_settings(
                            token_user_id, user_privacy_settings, db
                        )
                        counts["user_privacy_settings"] += 1

                # d) import activities JSON
                elif path == "data/activities.json":
                    activities = json.loads(zipf.read(entry))
                    laps = (
                        json.loads(zipf.read("data/activity_laps.json"))
                        if "data/activity_laps.json" in zipf.namelist()
                        else []
                    )
                    sets = (
                        json.loads(zipf.read("data/activity_sets.json"))
                        if "data/activity_sets.json" in zipf.namelist()
                        else []
                    )
                    streams = (
                        json.loads(zipf.read("data/activity_streams.json"))
                        if "data/activity_streams.json" in zipf.namelist()
                        else []
                    )
                    steps = (
                        json.loads(zipf.read("data/activity_workout_steps.json"))
                        if "data/activity_workout_steps.json" in zipf.namelist()
                        else []
                    )
                    exercise_titles = (
                        json.loads(zipf.read("data/activity_exercise_titles.json"))
                        if "data/activity_exercise_titles.json" in zipf.namelist()
                        else []
                    )
                    for activity in activities:
                        # ensure activity has the correct user_id on import
                        activity["user_id"] = token_user_id
                        activity["gear_id"] = (
                            gears_id_mapping.get(activity["gear_id"])
                            if activity.get("gear_id") in gears_id_mapping
                            else None
                        )
                        # create activity
                        new_activity = activities_crud.create_activity(activity, db)
                        activities_id_mapping[activity["id"]] = new_activity.id
                        counts["activities"] += 1
                        # create laps for the activity if available
                        if laps:
                            laps_for_activity = [
                                lap
                                for lap in laps
                                if lap.get("activity_id") == activity["id"]
                            ]
                            for lap in laps_for_activity:
                                lap["activity_id"] = new_activity.id
                            activity_laps_crud.create_activity_laps(
                                laps_for_activity, db
                            )
                            counts["activity_laps"] += 1
                        # create sets for the activity if available
                        if sets:
                            sets_for_activity = [
                                activity_set
                                for activity_set in sets
                                if activity_set.get("activity_id") == activity["id"]
                            ]
                            for activity_set in sets_for_activity:
                                activity_set["activity_id"] = new_activity.id
                            activity_sets_crud.create_activity_sets(
                                sets_for_activity, db
                            )
                            counts["activity_sets"] += 1
                        # create streams for the activity if available
                        if streams:
                            streams_for_activity = [
                                stream
                                for stream in streams
                                if stream.get("activity_id") == activity["id"]
                            ]
                            for stream in streams_for_activity:
                                stream["activity_id"] = new_activity.id
                            activity_streams_crud.create_activity_streams(
                                streams_for_activity, db
                            )
                            counts["activity_streams"] += 1
                        # create workout steps for the activity if available
                        if steps:
                            steps_for_activity = [
                                step
                                for step in steps
                                if step.get("activity_id") == activity["id"]
                            ]
                            for step in steps_for_activity:
                                step["activity_id"] = new_activity.id
                            activity_workout_steps_crud.create_activity_workout_steps(
                                steps_for_activity, db
                            )
                            counts["activity_workout_steps"] += 1
                        # create exercise titles for the activity if available
                        if exercise_titles:
                            exercise_titles_for_activity = [
                                title
                                for title in exercise_titles
                                if title.get("activity_id") == activity["id"]
                            ]
                            for title in exercise_titles_for_activity:
                                title["activity_id"] = new_activity.id
                            activity_exercise_titles_crud.create_activity_exercise_titles(
                                exercise_titles_for_activity, db
                            )
                            counts["activity_exercise_titles"] += 1

                # e) import activity files if available to disk
                if path.lower().endswith((".gpx", ".fit")):
                    file_id, ext = os.path.splitext(path)
                    new_id = (
                        activities_id_mapping.get(file_id)
                        if file_id in activities_id_mapping
                        else None
                    )
                    new_file_name = f"{new_id}.{ext.lstrip('.')}"
                    activity_files = os.path.join(
                        core_config.FILES_PROCESSED_DIR, new_file_name
                    )
                    with open(activity_files, "wb") as activity_files_folder:
                        activity_files_folder.write(zipf.read(entry))
                    counts["activity_files"] += 1

                # f) import health CSV
                elif path == "data/health_data.json":
                    health_data = json.loads(zipf.read(entry))
                    if health_data:
                        # ensure health data has the correct user_id on import
                        for data in health_data:
                            data["user_id"] = token_user_id
                            # create health data
                            health_crud.create_health_data(data, db)
                            counts["health_data"] += 1

                # g) import health targets JSON
                elif path == "data/health_targets.json":
                    health_targets = json.loads(zipf.read(entry))
                    if health_targets:
                        # ensure health targets has the correct user_id on import
                        for target in health_targets:
                            target["user_id"] = token_user_id
                            # create health target
                            health_targets_crud.edit_health_target(
                                target, token_user_id, db
                            )
                            counts["health_targets"] += 1 """
        return {"detail": "Import completed", "imported": counts}

    except Exception as err:
        core_logger.print_to_log(
            f"Error in import_profile_data: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Import failed: {err}",
        ) from err
