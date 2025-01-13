from fastapi import APIRouter, HTTPException, status

import core.config as core_config
import core.utils as core_utils

# Define the API router
router = APIRouter()


@router.get(
    core_config.ROOT_PATH + "/about",
)
async def about():
    return {
        "name": "Endurain API",
        "version": core_config.API_VERSION,
        "license": {
            "name": core_config.LICENSE_NAME,
            "identifier": core_config.LICENSE_IDENTIFIER,
            "url": core_config.LICENSE_URL,
        },
    }


@router.get("/api/v1/{catchall:path}", include_in_schema=False)
def api_not_found():
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="API endpoint not found",
    )


@router.get("/user_images/{user_img}", include_in_schema=False)
def user_img_return(
    user_img: str,
):
    return core_utils.return_user_img_path(user_img)


@router.get("/{path:path}", include_in_schema=False)
def frontend_not_found(
    path: str,
):
    if "." in path.split("/")[-1]:
        return core_utils.return_frontend_index(path)
    return core_utils.return_frontend_index("index.html")
