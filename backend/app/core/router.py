from fastapi import APIRouter

import core.config as core_config

# Define the API router
router = APIRouter()


@router.get(
    "/about",
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
