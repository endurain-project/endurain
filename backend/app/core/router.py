from fastapi import APIRouter

import core.config as core_config
import core.utils as core_utils

# Define the API router
router = APIRouter()


@router.get("/login", include_in_schema=False)
async def read_index_login():
    return core_utils.return_frontend_index()


@router.get("/activity/{activity_id}", include_in_schema=False)
async def read_index_activity():
    return core_utils.return_frontend_index()


@router.get("/gears", include_in_schema=False)
async def read_index_gears():
    return core_utils.return_frontend_index()


@router.get("/gear/{gear_id}", include_in_schema=False)
async def read_index_gear():
    return core_utils.return_frontend_index()


@router.get("/health", include_in_schema=False)
async def read_index_health():
    return core_utils.return_frontend_index()


@router.get("/user/{user_id}", include_in_schema=False)
async def read_index_user():
    return core_utils.return_frontend_index()


@router.get("/settings", include_in_schema=False)
async def read_index_settings():
    return core_utils.return_frontend_index()


@router.get("/strava/callback", include_in_schema=False)
async def read_index_strava_callback():
    return core_utils.return_frontend_index()


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
    return core_utils.return_frontend_index()


@router.get("/{catchall:path}", include_in_schema=False)
def api_not_found():
    return core_utils.return_frontend_index()
