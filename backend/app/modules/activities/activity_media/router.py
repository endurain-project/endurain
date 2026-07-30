"""API routes for activity media uploads and management.

Thin HTTP adapter: authorization, storage naming and file cleanup live in
:mod:`modules.activities.activity_media.service`.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Security, UploadFile, status
from sqlalchemy.orm import Session

import core.database as core_database
import modules.activities.activity_media.dependencies as activities_media_dependencies
import modules.activities.activity_media.schema as activity_media_schema
import modules.activities.activity_media.service as activity_media_service
import modules.auth.dependencies as auth_dependencies

# Define the API router
router = APIRouter()


@router.get(
    "/media",
    response_model=list[activity_media_schema.ActivityMedia] | None,
)
def read_activities_media_user(
    activity_id: int,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> list[activity_media_schema.ActivityMedia] | None:
    """
    Retrieve activity media records for an activity owned by the user.

    Args:
        activity_id: Activity ID to fetch media for.
        _validate_id: Activity ID validation dependency.
        _check_scopes: Scope validation dependency.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        List of ActivityMedia records, or None if there are no media or
        the activity is not accessible to the user.
    """
    return activity_media_service.list_activity_media(activity_id, token_user_id, db)


@router.post(
    "/media",
    response_model=activity_media_schema.ActivityMedia,
    status_code=status.HTTP_201_CREATED,
)
def upload_media(
    file: UploadFile,
    activity_id: int,
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["activities:write"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> activity_media_schema.ActivityMedia:
    """
    Upload an image file to associate with an activity.

    The file is validated by magic-number (not extension) and size limits
    via the centralized image upload helper, stored under the configured
    ``ACTIVITY_MEDIA_DIR``, and registered in the database.

    Args:
        file: Uploaded image file.
        activity_id: Activity ID the media belongs to.
        _validate_id: Activity ID validation dependency.
        _check_scopes: Scope validation dependency.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        The newly created ActivityMedia record.

    Raises:
        HTTPException:
            - 404 Not Found: If the activity is not owned by the user.
            - 400 Bad Request: If image validation fails.
            - 415 Unsupported Media Type: If the extension is rejected.
            - 409 Conflict: If a media with the same path already exists.
            - 500 Internal Server Error: For unexpected I/O or DB errors.
    """
    return activity_media_service.store_activity_media(activity_id, token_user_id, file, db)


@router.delete(
    "/media/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_activity_media(
    activity_id: int,
    media_id: int,
    _validate_id: Annotated[Callable, Depends(activities_media_dependencies.validate_media_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> None:
    """
    Delete an activity media record and remove its file from disk.

    Args:
        activity_id: Activity the media must belong to.
        media_id: Activity media ID to delete.
        _validate_id: Media ID validation dependency.
        _check_scopes: Scope validation dependency.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException:
            - 404 Not Found: If the media is missing, does not belong to this
              activity, or its owning activity is not the user's.
            - 500 Internal Server Error: For database errors.
    """
    activity_media_service.delete_activity_media(activity_id, media_id, token_user_id, db)
