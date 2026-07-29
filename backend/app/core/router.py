"""Core metadata and static fallback routes."""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

import core.config as core_config
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


@router.get("/user_images/{user_img}", response_class=FileResponse)
def user_img_return(
    user_img: str,
) -> FileResponse:
    """
    Retrieves the file path for a user's image.

    Args:
        user_img (str): The filename or identifier of the user's image.

    Returns:
        str: The file path to the user's image.

    Raises:
        HTTPException: If the image path cannot be found.
    """
    path = core_utils.return_user_img_path(user_img)

    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User image not found",
        )

    return path


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


# NOTE: there is deliberately no ``/activity_media/{media}`` or
# ``/activity_thumbnails/{thumbnail}`` route here. Both blob kinds are private
# user data and are served only by their token-gated routes
# (modules.activities.activity_media.public_router and
# modules.activities.activity_thumbnail.router). A filename-addressed route next
# to them is a full bypass of that gate, which is what these two used to be.


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
    return core_utils.return_frontend_index("index.html")
