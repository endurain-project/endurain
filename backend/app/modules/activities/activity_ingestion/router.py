"""FastAPI routes for activity ingestion (file upload, bulk import, provider refresh).

These endpoints stay under the ``/activities`` prefix but live here (not in
``activity/router.py``) because they drive the format/provider-aware ingestion flows:
file parsing via :mod:`~modules.activities.activity_ingestion.orchestrator` and live
provider sync via the Strava/Garmin clients. Keeping them here leaves the activities
core router fully parser- and provider-agnostic (enforced by the import-linter contract
``activities-parsing-boundary``).
"""

import os
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Security,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import modules.activities.activity.schema as activities_schema
import modules.activities.activity_ingestion.bulk_import_subscribers as activity_bulk_import_subscribers
import modules.activities.activity_ingestion.orchestrator as orchestrator
import modules.auth.dependencies as auth_dependencies
import modules.garmin.activity_utils as garmin_activity_utils
import modules.strava.activity_utils as strava_activity_utils
import modules.websocket.manager as websocket_manager

# Bulk import endpoint (JWT auth)
router = APIRouter()

# Separate router for upload endpoint that supports
# both JWT and API key authentication
api_upload_router = APIRouter()

# Define the thread pool executor with 2 workers
executor = ThreadPoolExecutor(max_workers=2)


@api_upload_router.post(
    "/upload",
    status_code=201,
    response_model=list[activities_schema.Activity],
)
def create_activity_with_uploaded_file(
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
):
    """
    Upload an activity file (GPX, FIT, TCX, GZ).

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
        List of created activity objects.
    """
    return orchestrator.parse_and_store_activity_from_uploaded_file(token_user_id, file, db)


@router.post(
    "/bulk-import",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=dict[str, str],
)
def create_activity_with_bulk_import(
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    try:
        # Get time of import initiation to pass to function for recording in import_data
        import_time = datetime.now(UTC).isoformat()

        core_logger.print_to_log_and_console(f"Bulk import initiated at {import_time}.", "info")

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
                core_logger.print_to_log_and_console(
                    f"Skipping file {file_path} due to not having a supported file extension. Supported extensions are: {supported_file_formats}."
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
                    core_logger.print_to_log_and_console(
                        f"Skipping file {file_path}: {err.detail}",
                        "warning",
                    )
                    continue

                files_to_process.append(file_path)
                # Log the file being processed
                core_logger.print_to_log_and_console(f"Queuing file for processing: {file_path}", "info")

        # Hand each validated file off for background processing. When durable jobs
        # are enabled, publish one durable job per file (A9): the event is staged in
        # the transactional outbox on this request's session, then the relay fans it
        # into a retryable, dead-letterable processing_jobs row drained by the
        # in-process worker (local) or the worker fleet (distributed) — a crash
        # mid-import no longer drops in-flight files, and a failing file retries then
        # dead-letters (moved to the import-error dir) instead of vanishing on the
        # first error. When durable jobs are off there is no worker to drain the
        # queue, so fall back to the legacy module-level threadpool (one task
        # processing all files, exceptions surfaced via a done-callback).
        if core_config.settings.JOBS_ENABLED:
            for file_path in files_to_process:
                activity_bulk_import_subscribers.publish_bulk_import_file(file_path, token_user_id, import_time, db)
        else:
            future = executor.submit(
                orchestrator.process_all_files_sync,
                token_user_id,
                files_to_process,
                import_initiated_time=import_time,
            )

            def _log_bulk_import_failure(fut: Future) -> None:
                exc = fut.exception()
                if exc is not None and isinstance(exc, Exception):
                    core_logger.print_to_log(
                        f"Bulk import background task failed: {exc}",
                        "error",
                        exc=exc,
                    )

            future.add_done_callback(_log_bulk_import_failure)

        # Log a success message that explains processing will continue elsewhere.
        core_logger.print_to_log_and_console(
            "Bulk import initiated for all files found in the bulk_import directory. Processing of files will continue in the background."
        )

        # Return a success message
        return {
            "detail": (
                "Bulk import initiated for all files found in the "
                "bulk_import directory. Processing of files will "
                "continue in the background."
            )
        }
    except (OSError, RuntimeError) as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in create_activity_with_bulk_import: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


@router.get(
    "/refresh",
    response_model=list[activities_schema.Activity] | None,
)
async def refresh_activities(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
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

    The one documented ``async`` route (plan §7.3): it awaits the provider HTTP
    clients, which are not yet reworked. It lives in the ingestion layer (not the
    activities core) because it depends on the Strava/Garmin provider clients — the
    core router stays provider-agnostic.
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
    activities = [activity for activity in activities if activity is not None]

    # Return the activities or None if the list is empty
    return activities if activities else None
