"""FastAPI routes for activity ingestion (file upload + bulk import).

These endpoints stay under the ``/activities`` prefix but live here (not in
``activity/router.py``) because they drive the file-format-aware ingestion flow in
:mod:`~modules.activities.activity_ingestion.orchestrator`, keeping the activities core
router parser-agnostic.
"""

import asyncio
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from functools import partial
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
import modules.activities.activity_ingestion.orchestrator as orchestrator
import modules.auth.dependencies as auth_dependencies
import modules.websocket.manager as websocket_manager

# Bulk import endpoint (JWT auth)
router = APIRouter()

# Separate router for upload endpoint that supports
# both JWT and API key authentication
api_upload_router = APIRouter()

# Define the thread pool executor with 2 workers
executor = ThreadPoolExecutor(max_workers=2)


@api_upload_router.post(
    "/create/upload",
    status_code=201,
    response_model=list[activities_schema.Activity],
)
async def create_activity_with_uploaded_file(
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
    ws_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
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
        ws_manager: WebSocket manager for real-time
            notifications.
        db: Database session dependency.

    Returns:
        List of created activity objects.
    """
    return await orchestrator.parse_and_store_activity_from_uploaded_file(token_user_id, file, ws_manager, db)


@router.post(
    "/create/bulkimport",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=dict[str, str],
)
async def create_activity_with_bulk_import(
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    ws_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
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
                    await core_file_uploads.validate_local_file(
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

        # Submit ONE task that processes all files. Use the running
        # loop (get_event_loop is deprecated in 3.12+ when no loop
        # exists) and attach a done-callback so executor exceptions
        # are surfaced via the logger instead of being silently lost.
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(
            executor,
            partial(
                orchestrator.process_all_files_sync,
                token_user_id,
                files_to_process,
                ws_manager,
                import_initiated_time=import_time,
            ),
        )

        def _log_bulk_import_failure(fut: asyncio.Future) -> None:
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
