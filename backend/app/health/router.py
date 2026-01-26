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
    response_model=health_schema.HealthImportResponse,
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
    _websocket_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    try:
        return await health_utils.parse_and_store_health_from_uploaded_file(
            token_user_id, file, db
        )
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in create_health_with_uploaded_file: {err}", "error", exc=err
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error",
        ) from err