from fastapi import APIRouter

import core.config as core_config

# Define the API router
router = APIRouter()

@router.get(
    "/about",
)
async def about(
):
    # Return the gear
    return {
        "name": "Endurain API",
        "version": core_config.API_VERSION,
        "license": {
            "name": "GNU General Public License v3.0",
            "identifier": "GPL-3.0-or-later",
            "url": "https://spdx.org/licenses/GPL-3.0-or-later.html",
        },
    }