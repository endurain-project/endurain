"""API routes for activity media uploads and management.

Thin HTTP adapter: authorization, storage naming and file cleanup live in
:mod:`modules.activities.activity_media.service`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Security, UploadFile, status

import core.dependencies as core_dependencies
import core.file_uploads as core_file_uploads
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_media.schema as activity_media_schema
import modules.activities.activity_media.service as activity_media_service
import modules.auth.dependencies as auth_dependencies

# Define the API router
router = APIRouter()


@router.get(
    "/media",
    response_model=activity_media_schema.ActivityMediaPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def list_activity_media(
    activity_id: activity_dependencies.ActivityId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.child_page_params)],
) -> activity_media_schema.ActivityMediaPage:
    """Return one page of the media attached to an activity owned by the user.

    The page is empty when the activity has no media or is not accessible to the
    caller.
    """
    return activity_media_service.list_activity_media(
        activity_id, token_user_id, db, page_number=page.page_number, num_records=page.num_records
    )


@router.post(
    "/media",
    response_model=activity_media_schema.ActivityMediaRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def create_activity_media(
    request: Request,
    file: UploadFile,
    activity_id: activity_dependencies.ActivityId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    storage: core_dependencies.Storage,
) -> activity_media_schema.ActivityMediaRead:
    """Upload an image file to associate with an activity.

    The file is validated by magic number (not extension) and size limits via
    the centralized image upload helper before the ownership check, stored through the platform
    ``StorageProvider`` under a server-generated key, and registered in the
    database. The response carries a signed URL; the blob itself has no public
    path.

    Rate limited on the ``UPLOAD`` tier: it is an authenticated endpoint that
    writes caller-supplied bytes to storage, so without a cap a single account
    can fill the media volume.

    Not found when the activity is not the caller's, rejected when the extension
    is unsupported, and a conflict when a media with the same path already exists.
    """
    # The route is synchronous and runs on a worker thread, so the blocking read
    # never touches the event loop.
    data = core_file_uploads.read_validated_upload_sync(file, kind=core_file_uploads.UploadKind.IMAGE)
    return activity_media_service.store_activity_media(activity_id, token_user_id, file.filename, data, storage, db)


@router.delete(
    "/media/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_activity_media(
    request: Request,
    activity_id: activity_dependencies.ActivityId,
    media_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    storage: core_dependencies.Storage,
) -> None:
    """Delete an activity media record and remove its stored blob.

    Not found when the media is missing, does not belong to this activity, or its
    activity is not the caller's.
    """
    activity_media_service.delete_activity_media(activity_id, media_id, token_user_id, storage, db)
