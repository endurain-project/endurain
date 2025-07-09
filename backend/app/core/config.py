import os

import core.logger as core_logger

# Constant related to version
API_VERSION = "v0.12.7"
LICENSE_NAME = "GNU Affero General Public License v3.0 or later"
LICENSE_IDENTIFIER = "AGPL-3.0-or-later"
LICENSE_URL = "https://spdx.org/licenses/AGPL-3.0-or-later.html"
ROOT_PATH = "/api/v1"
FRONTEND_DIR = "/app/frontend/dist"
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
TZ = os.getenv("TZ", "UTC")
USER_IMAGES_DIR = "user_images"
SERVER_IMAGES_DIR = "server_images"
FILES_DIR = "files"
FILES_PROCESSED_DIR = "files/processed"
FILES_BULK_IMPORT_DIR = "files/bulk_import"
SUPPORTED_FILE_FORMATS = [".fit", ".gpx"]  # used to screen bulk import files

def check_required_env_vars():
    required_env_vars = [
        "DB_PASSWORD",
        "SECRET_KEY",
        "FERNET_KEY",
        "ENDURAIN_HOST",
        "GEOCODES_MAPS_API",
    ]

    for var in required_env_vars:
        if var not in os.environ:
            core_logger.print_to_log_and_console(f"Missing required environment variable: {var}", "error")
            raise EnvironmentError(f"Missing required environment variable: {var}")
