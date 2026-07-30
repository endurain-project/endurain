"""API routes for activity media uploads and management.

Thin HTTP adapter: authorization, storage naming and file cleanup live in
:mod:`modules.activities.activity_media.service`.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Security, UploadFile, status
from sqlalchemy.orm import Session

import core.database as core_database
import core.rate_limit as core_rate_limit
import modules.activities.activity_media.dependencies as activities_media_dependencies
import modules.activities.activity_media.schema as activity_media_schema
import modules.activities.activity_media.service as activity_media_service
import modules.auth.dependencies as auth_dependencies

# Define the API router
router = APIRouter()


@router.get(
    "/media",
    response_model=list[activity_media_schema.ActivityMedia],
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
) -> list[activity_media_schema.ActivityMedia]:
    """
    Retrieve activity media records for an activity owned by the user.

    Returns an empty list when the activity has no media or is not accessible to
    the caller — previously ``200 null``, which made a collection endpoint answer
    with a scalar and forced every client to null-check it.

    Args:
        activity_id: Activity ID to fetch media for.
        _check_scopes: Scope validation dependency.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        The activity's media records, empty when there are none.
    """
    return activity_media_service.list_activity_media(activity_id, token_user_id, db)


@router.post(
    "/media",
    response_model=activity_media_schema.ActivityMedia,
    status_code=status.HTTP_201_CREATED,
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def upload_media(
    request: Request,
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

    The file is validated by magic number (not extension) and size limits via
    the centralized image upload helper, stored through the platform
    ``StorageProvider`` under a server-generated key, and registered in the
    database. The response carries a signed URL; the blob itself has no public
    path.

    Rate limited on the ``UPLOAD`` tier: it is an authenticated endpoint that
    writes caller-supplied bytes to storage, so without a cap a single account
    can fill the media volume.

    Args:
        request: Incoming request, required by the rate limiter.
        file: Uploaded image file.
        activity_id: Activity ID the media belongs to.
        _check_scopes: Scope validation dependency.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        The newly created ActivityMedia record.

    Raises:
        NotFoundError: If the activity is not owned by the user.
        UnsupportedMediaTypeError: If the extension is rejected.
        ConflictError: If a media with the same path already exists.
    """
    return activity_media_service.store_activity_media(activity_id, token_user_id, file, db)


@router.delete(
    "/media/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_activity_media(
    request: Request,
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
    Delete an activity media record and remove its stored blob.

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
        NotFoundError: If the media is missing, does not belong to this activity,
            or its owning activity is not the user's.
    """
    activity_media_service.delete_activity_media(activity_id, media_id, token_user_id, db)
