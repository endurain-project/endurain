import os
import threading

import core.logger as core_logger

# Constant related to version
API_VERSION = "v0.14.0"
LICENSE_NAME = "GNU Affero General Public License v3.0 or later"
LICENSE_IDENTIFIER = "AGPL-3.0-or-later"
LICENSE_URL = "https://spdx.org/licenses/AGPL-3.0-or-later.html"
ROOT_PATH = "/api/v1"
FRONTEND_DIR = "/app/frontend/dist"
ENVIRONMENT = os.getenv("ENVIRONMENT", "production").lower()
TZ = os.getenv("TZ", "UTC")
FILES_DIR = "data/activity_files"
FILES_BULK_IMPORT_DIR = "data/activity_files/bulk_import"
FILES_PROCESSED_DIR = "data/activity_files/processed"
ACTIVITY_MEDIA_DIR = "data/activity_media"
USER_IMAGES_DIR = "data/user_images"
SERVER_IMAGES_DIR = "data/server_images"
REVERSE_GEO_PROVIDER = os.getenv("REVERSE_GEO_PROVIDER", "geocode").lower()
PHOTON_API_HOST = os.getenv("PHOTON_API_HOST", "photon.komoot.io").lower()
PHOTON_API_USE_HTTPS = os.getenv("PHOTON_API_USE_HTTPS", "true").lower() == "true"
GEOCODES_MAPS_API = os.getenv("GEOCODES_MAPS_API", "changeme")
try:
    GEOCODES_MAPS_RATE_LIMIT = float(os.getenv("GEOCODES_MAPS_RATE_LIMIT", "1"))
except ValueError:
    core_logger.print_to_log_and_console(
        "Invalid GEOCODES_MAPS_RATE_LIMIT value, expected an int; defaulting to 1.0",
        "warning",
    )
    GEOCODES_MAPS_RATE_LIMIT = 1.0
GEOCODES_MIN_INTERVAL = (
    1.0 / GEOCODES_MAPS_RATE_LIMIT if GEOCODES_MAPS_RATE_LIMIT > 0 else 0
)
GEOCODES_LOCK = threading.Lock()
GEOCODES_LAST_CALL = 0.0
SUPPORTED_FILE_FORMATS = [
    ".fit",
    ".gpx",
    ".tcx",
    ".gz",
]  # used to screen bulk import files


def check_required_env_vars():
    required_env_vars = [
        "DB_PASSWORD",
        "SECRET_KEY",
        "FERNET_KEY",
        "ENDURAIN_HOST",
    ]

    for var in required_env_vars:
        if var not in os.environ:
            core_logger.print_to_log_and_console(
                f"Missing required environment variable: {var}", "error"
            )
            raise EnvironmentError(f"Missing required environment variable: {var}")
