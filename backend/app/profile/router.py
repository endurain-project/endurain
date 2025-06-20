import os
import json
import csv

from io import BytesIO, StringIO
from pathlib import Path
from zipfile import ZipFile

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile
from sqlalchemy.orm import Session

import users.user.schema as users_schema
import users.user.crud as users_crud
import users.user.utils as users_utils

import users.user_integrations.crud as user_integrations_crud

import users.user_privacy_settings.crud as users_privacy_settings_crud
import users.user_privacy_settings.schema as users_privacy_settings_schema

import session.security as session_security
import session.crud as session_crud

import core.database as core_database

import users.user_privacy_settings.crud as users_privacy_settings_crud
import users.user_privacy_settings.schema as users_privacy_settings_schema

import activities.activity.crud as activities_crud
import health_data.crud as health_crud

PROCESSED_DIR = os.getenv("PROCESSED_DIR", "files/processed")

# Define the API router
router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "files" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR = str(PROCESSED_DIR)


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
            detail="Could not validate credentials (user not found)",
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
async def export_user_data(
    token_user_id: int = Depends(session_security.get_user_id_from_access_token),
    db: Session = Depends(core_database.get_db),
):
    # Verify user
    if not users_crud.get_user_by_id(token_user_id, db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    buf = BytesIO()
    with ZipFile(buf, "w") as zipf:
        # 1) GPX/FIT track files
        user_dir = os.path.join(PROCESSED_DIR, str(token_user_id))
        if os.path.isdir(user_dir):
            for fname in os.listdir(user_dir):
                if fname.lower().endswith((".gpx", ".fit")):
                    zipf.write(os.path.join(user_dir, fname), arcname=f"tracks/{fname}")

        # 2) Activities JSON
        acts = activities_crud.get_user_activities(token_user_id, db) or []
        zipf.writestr("data/activities.json", json.dumps(acts, default=str))

        # 3) Health CSV
        entries = health_crud.get_all_health_data_by_user_id(token_user_id, db) or []
        if entries:
            sio = StringIO()
            # take non-private fields from the first model instance
            fieldnames = [k for k in entries[0].__dict__ if not k.startswith("_")]
            writer = csv.DictWriter(sio, fieldnames=fieldnames)
            writer.writeheader()
            for e in entries:
                writer.writerow({k: getattr(e, k) for k in fieldnames})
            zipf.writestr("data/health.csv", sio.getvalue())

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="user_{token_user_id}_export.zip"'
        },
    )


@router.post("/import")
async def import_user_data(
    file: UploadFile,
    token_user_id: int = Depends(session_security.get_user_id_from_access_token),
    db: Session = Depends(core_database.get_db),
):
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file must be a .zip")

    user_dir = os.path.join(PROCESSED_DIR, str(token_user_id))
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
