from fastapi import APIRouter, HTTPException, status

import core.config as core_config
import core.utils as core_utils

# Define the API router
router = APIRouter()


@router.get(
    core_config.ROOT_PATH + "/about",
)
async def about():
    """
    Returns metadata information about the Endurain API.

    Returns:
        dict: A dictionary containing the API name, version, and license details.
    """
    return {
        "name": "Endurain API",
        "version": core_config.API_VERSION,
        "license": {
            "name": core_config.LICENSE_NAME,
            "identifier": core_config.LICENSE_IDENTIFIER,
            "url": core_config.LICENSE_URL,
        },
    }


@router.get("/user_images/{user_img}")
def user_img_return(
    user_img: str,
):
    """
    Retrieves the file path for a user's image.

    Args:
        user_img (str): The filename or identifier of the user's image.

    Returns:
        str: The file path to the user's image.

    Raises:
        HTTPException: If the image path cannot be found, raises a 404 error.
    """
    path = core_utils.return_user_img_path(user_img)

    # If the path is None, raise a 404 error
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User image not found",
        )

    # Return the user image path
    return path


@router.get("/server_images/{server_img}")
def server_img_return(
    server_img: str,
):
    """
    Retrieves the file path for a given server image.

    Args:
        server_img (str): The identifier or filename of the server image.

    Returns:
        str: The file path to the server image.

    Raises:
        HTTPException: If the server image path cannot be found, raises a 404 error.
    """
    # Get the server image path
    path = core_utils.return_server_img_path(server_img)

    # If the path is None, raise a 404 error
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server image not found",
        )

    # Return the server image path
    return path


@router.get("/activity_media/{media}")
def activity_media_return(
    media: str,
):
    """
    Retrieves the server path for a given activity media file.

    Args:
        media (str): The name or identifier of the activity media file.

    Returns:
        str: The server path to the activity media file.

    Raises:
        HTTPException: If the media file is not found, raises a 404 error.
    """
    # Get the server image path
    path = core_utils.return_activity_media_path(media)

    # If the path is None, raise a 404 error
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity media not found",
        )

    # Return the activity media path
    return path


@router.get("/{path:path}", include_in_schema=False)
def frontend_not_found(
    path: str,
):
    """
    Handles requests for frontend resources and returns the appropriate index file.

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
