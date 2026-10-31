"""Core metadata and static fallback routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.utils as core_utils

# Define the API router
router = APIRouter()


class LicenseInfo(BaseModel):
    """
    API license metadata.

    Attributes:
        name: License display name.
        identifier: SPDX license identifier.
        url: Public license URL.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    identifier: str
    url: str


class AboutResponse(BaseModel):
    """
    API metadata returned by the about endpoint.

    Attributes:
        name: API display name.
        version: API version string.
        license: License metadata.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    license: LicenseInfo


@router.get(
    core_config.ROOT_PATH + "/about",
    response_model=AboutResponse,
    status_code=status.HTTP_200_OK,
)
async def about() -> AboutResponse:
    """
    Returns metadata information about the Endurain API.

    Returns:
        API name, version, and license details.
    """
    return AboutResponse(
        name="Endurain API",
        version=core_config.API_VERSION,
        license=LicenseInfo(
            name=core_config.LICENSE_NAME,
            identifier=core_config.LICENSE_IDENTIFIER,
            url=core_config.LICENSE_URL,
        ),
    )


@router.get(core_config.ROOT_PATH + "/health", status_code=status.HTTP_200_OK)
def health(db: Annotated[Session, Depends(core_database.get_db)]) -> dict[str, str]:
    """
    Liveness check that needs a database connection.

    Unlike ``/about``, this fails when the connection pool is exhausted or the
    database is unreachable, so orchestrators can detect a wedged instance.

    Args:
        db: Database session.

    Returns:
        ``{"status": "ok"}`` when the database answers.

    Raises:
        HTTPException: 503 when no connection can be obtained or the query fails.
    """
    try:
        db.execute(text("SELECT 1"))
    except Exception as err:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable") from err
    return {"status": "ok"}


@router.get("/server_images/{server_img}", response_class=FileResponse)
def server_img_return(
    server_img: str,
) -> FileResponse:
    """
    Retrieves the file path for a given server image.

    Args:
        server_img (str): The identifier or filename of the server image.

    Returns:
        str: The file path to the server image.

    Raises:
        HTTPException: If the server image path cannot be found.
    """
    path = core_utils.return_server_img_path(server_img)

    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server image not found",
        )

    return path


# NOTE: there is deliberately no ``/user_images/{user_img}``,
# ``/activity_media/{media}`` or ``/activity_thumbnails/{thumbnail}`` route here.
# All three serve private user data and are reachable only through their
# token-gated routes. A filename-addressed route beside them is a full bypass of
# that gate, which is what these used to be — and for user photos, stored as
# ``{user_id}.{ext}``, it enumerated the entire user base.


@router.get(
    "/{path:path}",
    include_in_schema=False,
    response_class=FileResponse,
)
def frontend_not_found(
    path: str,
) -> FileResponse:
    """
    Return the requested frontend asset or app index.

    Args:
        path (str): The requested resource path.

    Returns:
        Response: The frontend index file or the requested resource if found.

    Raises:
        HTTPException: If the requested resource is not found.
    """
    if "." in path.split("/")[-1]:
        result = core_utils.return_frontend_index(path)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found",
            )
        return result

    result = core_utils.return_frontend_index("index.html")
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Frontend index not found",
        )
    return result
