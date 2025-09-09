import os
import threading

import core.logger as core_logger

# Constant related to version
API_VERSION = "v0.14.0"
LICENSE_NAME = "GNU Affero General Public License v3.0 or later"
LICENSE_IDENTIFIER = "AGPL-3.0-or-later"
LICENSE_URL = "https://spdx.org/licenses/AGPL-3.0-or-later.html"
ROOT_PATH = "/api/v1"
FRONTEND_DIR = os.getenv("FRONTEND_DIR", "/app/frontend/dist")
BACKEND_DIR = os.getenv("BACKEND_DIR", "/app/backend")
DATA_DIR = os.getenv("DATA_DIR", "/app/backend/data")
LOGS_DIR = os.getenv("LOGS_DIR", f"{BACKEND_DIR}/logs")
USER_IMAGES_URL_PATH = "user_images"
USER_IMAGES_DIR = f"{DATA_DIR}/{USER_IMAGES_URL_PATH}"
SERVER_IMAGES_URL_PATH = "server_images"
SERVER_IMAGES_DIR = f"{DATA_DIR}/{SERVER_IMAGES_URL_PATH}"
FILES_DIR = os.getenv("FILES_DIR", f"{DATA_DIR}/activity_files")
ACTIVITY_MEDIA_DIR = os.getenv("ACTIVITY_MEDIA_DIR", f"{DATA_DIR}/activity_media")
FILES_PROCESSED_DIR = f"{FILES_DIR}/processed"
FILES_BULK_IMPORT_DIR = f"{FILES_DIR}/bulk_import"
FILES_BULK_IMPORT_IMPORT_ERRORS_DIR = f"{FILES_BULK_IMPORT_DIR}/import_errors"
ENVIRONMENT = os.getenv("ENVIRONMENT", "production").lower()
TZ = os.getenv("TZ", "UTC")
REVERSE_GEO_PROVIDER = os.getenv("REVERSE_GEO_PROVIDER", "nominatim").lower()
PHOTON_API_HOST = os.getenv("PHOTON_API_HOST", "photon.komoot.io").lower()
PHOTON_API_USE_HTTPS = os.getenv("PHOTON_API_USE_HTTPS", "true").lower() == "true"
NOMINATIM_API_HOST = os.getenv(
    "NOMINATIM_API_HOST", "nominatim.openstreetmap.org"
).lower()
NOMINATIM_API_USE_HTTPS = os.getenv("NOMINATIM_API_USE_HTTPS", "true").lower() == "true"
GEOCODES_MAPS_API = os.getenv("GEOCODES_MAPS_API", "changeme")
try:
    REVERSE_GEO_RATE_LIMIT = float(os.getenv("REVERSE_GEO_RATE_LIMIT", "1"))
except ValueError:
    core_logger.print_to_log_and_console(
        "Invalid REVERSE_GEO_RATE_LIMIT value, expected an int; defaulting to 1.0",
        "warning",
    )
    REVERSE_GEO_RATE_LIMIT = 1.0
REVERSE_GEO_MIN_INTERVAL = (
    1.0 / REVERSE_GEO_RATE_LIMIT if REVERSE_GEO_RATE_LIMIT > 0 else 0
)
REVERSE_GEO_LOCK = threading.Lock()
REVERSE_GEO_LAST_CALL = 0.0
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

    # Email is optional but warn if not configured
    email_vars = ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD"]
    for var in email_vars:
        if var not in os.environ:
            core_logger.print_to_log_and_console(
                f"Email not configured (missing: {var}). Password reset feature will not work.",
                "info",
            )

    for var in required_env_vars:
        if var not in os.environ:
            core_logger.print_to_log_and_console(
                f"Missing required environment variable: {var}", "error"
            )
            raise EnvironmentError(f"Missing required environment variable: {var}")


def check_required_dirs():
    required_dirs = [
        DATA_DIR,
        USER_IMAGES_DIR,
        SERVER_IMAGES_DIR,
        ACTIVITY_MEDIA_DIR,
        FILES_DIR,
        FILES_PROCESSED_DIR,
        FILES_BULK_IMPORT_DIR,
        FILES_BULK_IMPORT_IMPORT_ERRORS_DIR,
        LOGS_DIR,
    ]

    for required_dir in required_dirs:
        if not os.path.exists(required_dir):
            os.mkdir(required_dir)
        elif not os.path.isdir(required_dir):
            core_logger.print_to_log_and_console(
                f"Required directory is not a directory: {required_dir}", "error"
            )
            raise EnvironmentError(
                f"Required directory is not a directory: {required_dir}"
            )
