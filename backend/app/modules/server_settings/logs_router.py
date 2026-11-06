"""Admin routes for reading the server log."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Security, status
from fastapi.responses import FileResponse

import core.openapi_contract as core_openapi_contract
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.server_settings.logs_schema as logs_schema
import modules.server_settings.logs_service as logs_service

# Define the API router
router = APIRouter()


@router.get(
    "/status",
    response_model=logs_schema.LogsStatus,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["server_settings:logs"])],
)
def read_logs_status() -> logs_schema.LogsStatus:
    """Get whether the log viewer is available.

    Requires admin authentication with server_settings:logs scope.

    Returns:
        Whether the log can be read through the API on this deployment.
    """
    return logs_service.get_logs_status()


@router.get(
    "",
    response_model=logs_schema.LogPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["server_settings:logs"])],
)
def read_logs(
    num_records: Annotated[int, Query(ge=1, le=1000, description="Most records to return")] = 200,
    level: Annotated[logs_schema.LogLevel | None, Query(description="Lowest severity to include")] = None,
    search: Annotated[str | None, Query(max_length=200, description="Text a record must contain")] = None,
    cursor: Annotated[
        str | None,
        Query(
            pattern=r"^\d{1,18}$",
            description="`next_cursor` of an earlier page, to read only newer records",
        ),
    ] = None,
) -> logs_schema.LogPage:
    """Read records from the end of the server log.

    Requires admin authentication with server_settings:logs scope. Without ``cursor``
    the newest matching records are returned; pass the returned ``next_cursor`` as
    ``cursor`` to receive only what was written since.

    Args:
        num_records: Most records to return.
        level: Lowest severity to include.
        search: Case-insensitive text a record must contain.
        cursor: ``next_cursor`` of an earlier page.

    Returns:
        The matching records, oldest first, and the cursor for the next call.

    Raises:
        NotFoundError: 404 if the log viewer is not available on this deployment.
    """
    return logs_service.read_logs(num_records, level, search, None if cursor is None else int(cursor))


@router.get(
    "/download",
    response_class=FileResponse,
    responses=core_openapi_contract.binary_response("text/plain", description="The current log file."),
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["server_settings:logs"])],
)
def download_logs() -> FileResponse:
    """Download the current log file.

    Requires admin authentication with server_settings:logs scope. Rotated backups
    are not included.

    Returns:
        The log file as plain text.

    Raises:
        NotFoundError: 404 if the log viewer is not available or no log has been written.
    """
    return FileResponse(
        logs_service.get_log_file_path(),
        media_type="text/plain",
        filename=logs_service.LOG_FILE_NAME,
    )


@router.delete(
    "",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["server_settings:logs_clear"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def clear_logs(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
) -> None:
    """Empty the server log and delete its rotated backups.

    Requires admin authentication with server_settings:logs_clear scope. The action is
    recorded as the first line of the new log.

    Args:
        request: The HTTP request object.
        token_user_id: The requesting admin's user ID, from the access token.

    Raises:
        NotFoundError: 404 if the log viewer is not available on this deployment.
    """
    logs_service.clear_logs(token_user_id)
