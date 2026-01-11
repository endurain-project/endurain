import os
import asyncio
from typing import Annotated, Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import health.schema as health_schema
import health.utils as health_utils
import core.database as core_database
import core.logger as core_logger
import core.config as core_config
import auth.security as auth_security
import websocket.manager as websocket_manager
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Security,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

# Define the API router
router = APIRouter()

# Define the thread pool executor with 2 workers
executor = ThreadPoolExecutor(max_workers=2)


@router.post(
    "/create/upload",
    status_code=201,
    response_model=list[health_schema.HealthImportResponse],
)
async def create_health_with_uploaded_file(
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    file: UploadFile,
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["health:write"])
    ],
    websocket_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    try:
        return await health_utils.parse_and_store_activity_from_uploaded_file(
            token_user_id, file, websocket_manager, db
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in create_health_with_uploaded_file: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise err


@router.post(
    "/create/bulkimport",
)
async def create_activity_with_bulk_import(
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["health:write"])
    ],
    websocket_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
):
    try:
        core_logger.print_to_log_and_console("Bulk import initiated.")

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
            if file_extension not in supported_file_formats:
                core_logger.print_to_log_and_console(
                    f"Skipping file {file_path} due to not having a supported file extension. Supported extensions are: {supported_file_formats}."
                )
                # Might be good to notify the user, but background tasks cannot raise HTTPExceptions
                continue

            if os.path.isfile(file_path):
                files_to_process.append(file_path)
                # Log the file being processed
                core_logger.print_to_log_and_console(
                    f"Queuing file for processing: {file_path}"
                )

        # Submit ONE task that processes all files
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            executor,
            partial(
                health_utils.process_all_files_sync,
                token_user_id,
                files_to_process,
                websocket_manager,
            ),
        )

        # Log a success message that explains processing will continue elsewhere.
        core_logger.print_to_log_and_console(
            "Bulk import initiated for all files found in the bulk_import directory. Processing of files will continue in the background."
        )

        # Return a success message
        return {
            "Bulk import initiated for all files found in the bulk_import directory. Processing of files will continue in the background."
        }
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in create_activity_with_bulk_import: {err}", "error"
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err