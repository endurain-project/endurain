"""FastAPI routes for activity ingestion (file upload, bulk import, provider refresh).

These endpoints stay under the ``/activities`` prefix but live here (not in
``activity/router.py``) because they drive the format/provider-aware ingestion flows:
file parsing via :mod:`~modules.activities.activity_ingestion.upload_entry` and live
provider sync via the Strava/Garmin clients. Keeping them here leaves the activities
core router fully parser- and provider-agnostic (enforced by the import-linter contract
``activities-parsing-boundary``).
"""

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Security,
    UploadFile,
    status,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import core.rate_limit as core_rate_limit
import modules.activities.activity.schema as activities_schema
import modules.activities.activity_ingestion.background as activity_ingestion_background
import modules.activities.activity_ingestion.bulk_import_subscribers as activity_bulk_import_subscribers
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.activities.activity_ingestion.upload_crud as upload_crud
import modules.activities.activity_ingestion.upload_jobs as upload_jobs
import modules.auth.dependencies as auth_dependencies
import modules.garmin.activity_utils as garmin_activity_utils
import modules.strava.activity_utils as strava_activity_utils
import modules.websocket.manager as websocket_manager

logger = core_logger.get_logger(__name__)

# Bulk import endpoint (JWT auth)
router = APIRouter()

# Separate router for upload endpoint that supports
# both JWT and API key authentication
api_upload_router = APIRouter()


@api_upload_router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activity_ingestion_schema.ActivityUploadJob,
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def create_activity_with_uploaded_file(
    request: Request,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_user_id_from_auth),
    ],
    file: UploadFile,
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_auth_scopes,
            scopes=["activities:upload"],
        ),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> activity_ingestion_schema.ActivityUploadJob:
    """
    Upload an activity file (GPX, FIT, TCX, GZ) for import.

    Returns ``202`` once the file is stored and queued: parsing is seconds of
    CPU work, and doing it inline held a shared request thread for the duration.
    Poll ``GET /activities/upload/{job_id}`` for the outcome.

    Rejections that can be decided cheaply — unsupported extension, failed
    signature check, oversized body — still come back synchronously as a 4xx, so
    only files that plausibly import get a job.

    Accepts both JWT bearer token and API key
    authentication (X-API-Key header or ?api_key=
    query parameter). Requires the
    ``activities:upload`` scope.

    Args:
        token_user_id: Authenticated user ID.
        file: The activity file to upload.
        _check_scopes: Scope validation dependency.
        db: Database session dependency.

    Returns:
        The accepted upload job, in the pending state.
    """
    return upload_jobs.accept_upload(token_user_id, file, db)


@api_upload_router.get(
    "/upload/{job_id}",
    status_code=200,
    response_model=activity_ingestion_schema.ActivityUploadJob,
)
def get_activity_upload_job(
    job_id: str,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_user_id_from_auth),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_auth_scopes,
            scopes=["activities:upload"],
        ),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> activity_ingestion_schema.ActivityUploadJob:
    """
    Read the state of one of your uploads.

    Scoped to the caller: a job belonging to another user is reported as not
    found rather than forbidden, so the endpoint does not confirm that an id
    exists.

    Args:
        job_id: The upload job identifier returned by the upload route.
        token_user_id: Authenticated user ID.
        _check_scopes: Scope validation dependency.
        db: Database session dependency.

    Returns:
        The upload job.

    Raises:
        NotFoundError: If no such job belongs to the caller.
    """
    job = upload_crud.get_upload_job(job_id, token_user_id, db)
    if job is None:
        raise core_exceptions.NotFoundError("Upload job not found")
    return job


@router.post(
    "/bulk-import",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activities_schema.ActivityMessageResponse,
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def create_activity_with_bulk_import(
    request: Request,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> activities_schema.ActivityMessageResponse:
    try:
        # Get time of import initiation to pass to function for recording in import_data
        import_time = datetime.now(UTC).isoformat()

        logger.info(
            "Bulk import initiated",
            extra=core_logger.context(console=True, user_id=token_user_id, import_time=import_time),
        )

        # Ensure the 'bulk_import' directory exists
        bulk_import_dir = core_config.FILES_BULK_IMPORT_DIR
        os.makedirs(bulk_import_dir, exist_ok=True)

        # Grab list of supported file formats
        supported_file_formats = core_config.SUPPORTED_FILE_FORMATS

        # Iterate over each file in the 'bulk_import' directory
        files_to_process = []
        for filename in os.listdir(bulk_import_dir):
            file_path = os.path.join(bulk_import_dir, filename)

            # Check if file is one we can process
            _, file_extension = os.path.splitext(file_path)
            file_extension = file_extension.lower()
            if file_extension not in supported_file_formats:
                logger.info(
                    f"Skipping file {file_path} due to not having a supported file extension. Supported extensions are: {supported_file_formats}.",
                    extra=core_logger.context(console=True),
                )
                # Might be good to notify the user, but background tasks cannot raise HTTPExceptions
                continue

            if os.path.isfile(file_path):
                try:
                    # Choose validator kind based on extension; the
                    # supported-format check above guarantees one
                    # of the four kinds below.
                    validate_kind = (
                        core_file_uploads.UploadKind.GZIP
                        if file_extension == ".gz"
                        else core_file_uploads.UploadKind.ACTIVITY
                    )
                    core_file_uploads.validate_local_file_sync(
                        file_path,
                        kind=validate_kind,
                    )
                except HTTPException as err:
                    logger.warning(
                        "Skipping a bulk-import file that failed validation",
                        extra=core_logger.context(console=True, file=os.path.basename(file_path), reason=err.detail),
                    )
                    continue

                files_to_process.append(file_path)
                # Log the file being processed
                logger.info(
                    f"Queuing file for processing: {os.path.basename(file_path)}",
                    extra=core_logger.context(console=True),
                )

        # Hand each validated file off for background processing. When durable jobs
        # are enabled, publish one durable job per file: the events are staged in
        # the transactional outbox on this request's session and committed once,
        # then the relay fans them into retryable, dead-letterable processing_jobs
        # rows drained by the in-process worker (local) or the worker fleet
        # (distributed) — a crash mid-import no longer drops in-flight files, and a
        # failing file retries then dead-letters (moved to the import-error dir)
        # instead of vanishing on the first error. A staging failure propagates so
        # the caller gets a 500 rather than a 202 for files that were never queued.
        # When durable jobs are off there is no worker to drain the queue, so fall
        # back to the background thread pool owned by ``activity_ingestion.background``
        # (one task processing all files, exceptions surfaced via a done-callback).
        if core_config.settings.JOBS_ENABLED:
            activity_bulk_import_subscribers.publish_bulk_import_files(files_to_process, token_user_id, import_time, db)
        else:
            activity_ingestion_background.submit_bulk_import(token_user_id, files_to_process, import_time)

        # Log a success message that explains processing will continue elsewhere.
        logger.info(
            "Bulk import initiated for all files found in the bulk_import directory. Processing of files will continue in the background.",
            extra=core_logger.context(console=True),
        )

        # Return a success message
        return activities_schema.ActivityMessageResponse(
            detail=(
                "Bulk import initiated for all files found in the "
                "bulk_import directory. Processing of files will "
                "continue in the background."
            )
        )
    except (OSError, RuntimeError, SQLAlchemyError) as err:
        # Log the exception
        logger.error(
            "Error in create_activity_with_bulk_import",
            exc_info=err,
            extra=core_logger.context(user_id=token_user_id),
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


@router.post(
    "/refresh",
    response_model=list[activities_schema.Activity],
)
@core_rate_limit.limiter.limit(core_rate_limit.PROVIDER_SYNC)
async def refresh_activities(
    request: Request,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    ws_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
):
    """Fetch the last 24h of activities from the linked providers (Strava/Garmin).

    The one documented ``async`` route: it awaits the provider HTTP
    clients, which are not yet reworked. It lives in the ingestion layer (not the
    activities core) because it depends on the Strava/Garmin provider clients — the
    core router stays provider-agnostic.

    Returns an empty list when the providers had nothing new; it used to answer
    ``200 null``, which forced every client to null-check a collection endpoint.
    """
    # Set the activities to empty list
    activities = []

    # Get the strava activities for the user for the last 24h
    strava_activities = await strava_activity_utils.get_user_strava_activities_by_dates(
        start_date=datetime.now(UTC) - timedelta(days=1),
        end_date=datetime.now(UTC),
        user_id=token_user_id,
        db=db,
    )

    # Get the garmin activities for the user for the last 24h
    garmin_activities = await garmin_activity_utils.get_user_garminconnect_activities_by_dates(
        start_date=datetime.now(UTC) - timedelta(days=1),
        end_date=datetime.now(UTC),
        user_id=token_user_id,
        ws_manager=ws_manager,
        db=db,
    )

    # Extend the activities to the list
    if strava_activities is not None:
        activities.extend(strava_activities)

    if garmin_activities is not None:
        activities.extend(garmin_activities)

    # Filter out None values from the activities list
    return [activity for activity in activities if activity is not None]
