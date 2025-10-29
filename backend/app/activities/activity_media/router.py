import os

from typing import Annotated, Callable

from fastapi import APIRouter, Depends, Security, UploadFile
from sqlalchemy.orm import Session

import activities.activity.dependencies as activities_dependencies

import activities.activity_media.dependencies as activities_media_dependencies
import activities.activity_media.crud as activity_media_crud
import activities.activity_media.schema as activity_media_schema

import auth.security as auth_security

import core.config as core_config
import core.logger as core_logger
import core.database as core_database


# Define the API router
router = APIRouter()


@router.get(
    "/activity_id/{activity_id}",
    response_model=list[activity_media_schema.ActivityMedia] | None,
)
async def read_activities_media_user(
    activity_id: int,
    validate_id: Annotated[
        Callable, Depends(activities_dependencies.validate_activity_id)
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:read"])
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    return activity_media_crud.get_activity_media(activity_id, token_user_id, db)


@router.post(
    "/upload/activity_id/{activity_id}",
    status_code=201,
)
async def upload_media(
    file: UploadFile,
    activity_id: int,
    validate_id: Annotated[
        Callable, Depends(activities_dependencies.validate_activity_id)
    ],
    _check_scopes: Annotated[
        Callable,
        Security(auth_security.check_scopes, scopes=["activities:write"]),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    try:
        # Ensure the 'data/activity_media' directory exists
        upload_dir = core_config.ACTIVITY_MEDIA_DIR
        os.makedirs(upload_dir, exist_ok=True)

        new_file_name = f"{activity_id}_{file.filename}"

        # Build the full path with the name new_file_name
        file_path = os.path.join(upload_dir, new_file_name)

        # Save the uploaded file with the name new_file_name
        with open(file_path, "wb") as save_file:
            save_file.write(file.file.read())

        return activity_media_crud.create_activity_media(activity_id, file_path, db)
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in upload_login_photo: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise err


@router.delete(
    "/{media_id}",
)
async def delete_activity_media(
    media_id: int,
    validate_id: Annotated[
        Callable, Depends(activities_media_dependencies.validate_media_id)
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:write"])
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Delete the activity media from the database
    activity_media_crud.delete_activity_media(media_id, token_user_id, db)
