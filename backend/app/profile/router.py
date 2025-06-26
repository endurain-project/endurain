import os
import json
import csv

from io import BytesIO
import zipfile

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import users.user.schema as users_schema
import users.user.crud as users_crud
import users.user.utils as users_utils

import users.user_integrations.crud as user_integrations_crud

import users.user_default_gear.crud as user_default_gear_crud

import users.user_privacy_settings.crud as users_privacy_settings_crud
import users.user_privacy_settings.schema as users_privacy_settings_schema

import session.security as session_security
import session.crud as session_crud

import core.database as core_database
import core.config as core_config

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
    def sqlalchemy_obj_to_dict(obj):
        if hasattr(obj, "__table__"):
            return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
        return obj

    def write_json_to_zip(zipf, filename, data, ensure_ascii=False):
        if data:
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
                        file_path = os.path.join(root, file)
                        # Add file to the zip archive with relative path
                        arcname = os.path.relpath(file_path, core_config.FILES_PROCESSED_DIR)
                        zipf.write(file_path, arcname)

            # 2) Activities info plus laps, sets, streams, steps, exercise_titles JSON
            for activity in user_activities:
                # laps
                activity_laps = activity_laps_crud.get_activity_laps(
                    activity.id, token_user_id, db
                )
                if activity_laps:
                    laps.extend(activity_laps)
                # sets
                activity_sets = activity_sets_crud.get_activity_sets(
                    activity.id, token_user_id, db
                )
                if activity_sets:
                    sets.extend(activity_sets)
                # streams
                activity_streams = activity_streams_crud.get_activity_streams(
                    activity.id, token_user_id, db
                )
                if activity_streams:
                    streams.extend(activity_streams)
                # steps
                activity_workout_steps = (
                    activity_workout_steps_crud.get_activity_workout_steps(
                        activity.id, token_user_id, db
                    )
                )
                if activity_workout_steps:
                    steps.extend(activity_workout_steps)
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
        write_json_to_zip(zipf, "data/user.json", user_dict)

        # Check if the user has user images stored and added them to the zip
        for root, _, files in os.walk(core_config.USER_IMAGES_DIR):
            for file in files:
                file_id, ext = os.path.splitext(file)
                print(
                    f"Processing file: {file} with ID: {file_id} and extension: {ext}"
                )
                if str(user.id) == file_id:
                    print(f"Adding user image: {file} to zip")
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
        ]
        for data, filename in data_to_write:
            if data:
                if not isinstance(data, (list, tuple)):
                    data = [data]
                dicts = [sqlalchemy_obj_to_dict(item) for item in data]
                write_json_to_zip(zipf, filename, dicts)

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
async def import_user_data(
    file: UploadFile,
    token_user_id: int = Depends(session_security.get_user_id_from_access_token),
    db: Session = Depends(core_database.get_db),
):
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file must be a .zip")

    user_dir = os.path.join(core_config.FILES_PROCESSED_DIR, str(token_user_id))
    os.makedirs(user_dir, exist_ok=True)
    counts = {"tracks": 0, "activities": 0, "health_entries": 0}

    data = await file.read()
    try:
        with ZipFile(BytesIO(data)) as zipf:
            for entry in zipf.namelist():
                path = entry.replace("\\", "/")

                # a) write track files to disk
                if path.startswith("tracks/") and path.lower().endswith(
                    (".gpx", ".fit")
                ):
                    dst = os.path.join(user_dir, os.path.basename(path))
                    with open(dst, "wb") as out_f:
                        out_f.write(zipf.read(entry))
                    counts["tracks"] += 1

                # b) import activities JSON
                elif path == "data/activities.json":
                    acts = json.loads(zipf.read(entry))
                    for act in acts:
                        activities_crud.create_activity(act, db)
                        counts["activities"] += 1

                # c) import health CSV
                elif path == "data/health.csv":
                    rows = zipf.read(entry).decode("utf-8").splitlines()
                    for row in csv.DictReader(rows):
                        health_crud.create_health_data(token_user_id, row, db)
                        counts["health_entries"] += 1

    except Exception as ex:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Import failed: {ex}")

    return {"detail": "Import completed", "imported": counts}
