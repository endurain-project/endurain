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
from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
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
import modules.activities.activity_ingestion.ingestion_jobs as ingestion_jobs
import modules.activities.activity_ingestion.ingestion_jobs_crud as ingestion_jobs_crud
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.auth.dependencies as auth_dependencies

logger = core_logger.get_logger(__name__)

# Bulk import endpoint (JWT auth)
router = APIRouter()

# Separate router for upload endpoint that supports
# both JWT and API key authentication
api_upload_router = APIRouter()


@api_upload_router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activity_ingestion_schema.ActivityIngestionJob,
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
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            max_length=255,
            description=(
                "Optional client-generated key. Replaying a request with the same key returns "
                "the original job instead of importing the file again."
            ),
        ),
    ] = None,
) -> activity_ingestion_schema.ActivityIngestionJob:
    """
    Upload an activity file (GPX, FIT, TCX, GZ) for import.

    Returns ``202`` once the file is stored and queued: parsing is seconds of
    CPU work, and doing it inline held a shared request thread for the duration.
    Poll ``GET /activities/ingestion-jobs/{job_id}`` for the outcome.

    Rejections that can be decided cheaply — unsupported extension, failed
    signature check, oversized body — still come back synchronously as a 4xx, so
    only files that plausibly import get a job.

    Send an ``Idempotency-Key`` to make a retry safe: a client that never saw
    the 202 has no job id to poll, so replaying the upload is its only recovery,
    and without a key that replay would import the file a second time.

    Accepts both JWT bearer token and API key
    authentication (X-API-Key header or ?api_key=
    query parameter). Requires the
    ``activities:upload`` scope.

    Args:
        token_user_id: Authenticated user ID.
        file: The activity file to upload.
        _check_scopes: Scope validation dependency.
        db: Database session dependency.
        idempotency_key: Optional key identifying this request.

    Returns:
        The accepted upload job, in the pending state.
    """
    return ingestion_jobs.accept_upload(token_user_id, file, db, idempotency_key=idempotency_key)


@api_upload_router.get(
    "/ingestion-jobs/{job_id}",
    status_code=200,
    response_model=activity_ingestion_schema.ActivityIngestionJob,
)
def get_activity_ingestion_job(
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
) -> activity_ingestion_schema.ActivityIngestionJob:
    """
    Read the state of one of your ingestion requests.

    Serves both uploads and provider refreshes: the caller's question is the
    same either way, so there is one route rather than two near-identical ones.

    Scoped to the caller: a job belonging to another user is reported as not
    found rather than forbidden, so the endpoint does not confirm that an id
    exists.

    Args:
        job_id: The job identifier returned by the upload or refresh route.
        token_user_id: Authenticated user ID.
        _check_scopes: Scope validation dependency.
        db: Database session dependency.

    Returns:
        The ingestion job.

    Raises:
        NotFoundError: If no such job belongs to the caller.
    """
    job = ingestion_jobs_crud.get_ingestion_job(job_id, token_user_id, db)
    if job is None:
        raise core_exceptions.NotFoundError("Upload job not found")
    return job


def _warn_about_unowned_bulk_import_files(user_id: int) -> None:
    """Warn when importable files sit in the shared root instead of a user directory.

    Bulk import used to scan the shared root, so an existing install can have
    files there that will now be skipped. They are not imported on a guess about
    who owns them — that is the bug this isolation removes — but the operator is
    told exactly where to move them.

    Args:
        user_id: The user whose import was triggered, used to name the target.

    Returns:
        None.
    """
    root = core_config.FILES_BULK_IMPORT_DIR
    try:
        stranded = [
            name
            for name in os.listdir(root)
            if os.path.isfile(os.path.join(root, name))
            and os.path.splitext(name)[1].lower() in core_config.SUPPORTED_FILE_FORMATS
        ]
    except OSError:
        return

    if stranded:
        logger.warning(
            f"Skipping {len(stranded)} file(s) in the shared bulk-import root: they are not attributed "
            f"to any user. Move them into {core_config.bulk_import_dir_for(user_id)} to import them.",
            extra=core_logger.context(console=True, user_id=user_id, file_count=len(stranded)),
        )


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

        # Each user drops files into their own directory. Scanning the shared
        # root would import whatever anyone else left there and attribute it to
        # this caller.
        bulk_import_dir = core_config.bulk_import_dir_for(token_user_id)
        os.makedirs(bulk_import_dir, exist_ok=True)
        _warn_about_unowned_bulk_import_files(token_user_id)

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
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activity_ingestion_schema.ActivityIngestionJob,
)
@core_rate_limit.limiter.limit(core_rate_limit.PROVIDER_SYNC)
def refresh_activities(
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
) -> activity_ingestion_schema.ActivityIngestionJob:
    """Queue a sync of the last 24h from the linked providers (Strava/Garmin).

    Returns ``202`` with a job handle; poll
    ``GET /activities/ingestion-jobs/{job_id}`` for the outcome.

    This used to be the one ``async def`` route in activities, awaiting the
    provider clients inline. Everything synchronous on those paths — the
    integration lookups, the per-activity dedup reads — therefore ran on the
    event loop, where they stall every other request in the process instead of
    occupying a single worker thread. Running the sync as a job removes that
    class of bug rather than auditing for it: no provider code touches the loop
    any more.

    Args:
        token_user_id: Authenticated user ID.
        _check_scopes: Scope validation dependency.
        db: Database session dependency.

    Returns:
        The accepted refresh job, in the pending state.
    """
    return ingestion_jobs.accept_refresh(token_user_id, db)
