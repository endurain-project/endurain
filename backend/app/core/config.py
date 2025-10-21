import os
import threading
import stat
from pathlib import Path
from cryptography.fernet import Fernet

import core.logger as core_logger

# Constant related to version
API_VERSION = "v0.15.3"
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
STRAVA_BULK_IMPORT_BIKES_FILE = "bikes.csv"
STRAVA_BULK_IMPORT_SHOES_FILE = "shoes.csv"
STRAVA_BULK_IMPORT_SHOES_UNNAMED_SHOE = "Unnamed Shoe "
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


def read_secret(env_var_name: str, default_value: str | None = None) -> str | None:
    """
    Read a secret value from environment variables or secret files.
    This function implements a secure method to read configuration secrets following
    the Docker secrets pattern. It first attempts to read the value directly from
    an environment variable, and if not found, tries to read from a file specified
    by the corresponding `{env_var_name}_FILE` environment variable.
    Args:
        env_var_name (str): The name of the environment variable to read.
        default_value (str | None, optional): The default value to return if neither
            the environment variable nor the secret file is found. Defaults to None.
    Returns:
        str | None: The secret value from the environment variable, file, or the
            default value. Returns None if no value is found and no default is provided.
    Raises:
        EnvironmentError: If the secret file path is unsafe, not found, not a regular
            file, too large (>64KB), empty, or cannot be read due to I/O errors.
    Security Features:
        - Path traversal validation to prevent accessing unauthorized files
        - File size limit of 64KB to prevent memory exhaustion attacks
        - Warns if secret file has world-readable permissions
        - Does not expose sensitive file path details in error messages
        - Validates file existence and type before reading
    Examples:
        >>> # Read from environment variable
        >>> os.environ['DATABASE_PASSWORD'] = 'secret123'
        >>> read_secret('DATABASE_PASSWORD')
        'secret123'
        >>> # Read from secret file
        >>> os.environ['DATABASE_PASSWORD_FILE'] = '/run/secrets/db_password'
        >>> read_secret('DATABASE_PASSWORD')
        'secret123'
        >>> # Use default value when not found
        >>> read_secret('MISSING_VAR', 'default_value')
        'default_value'
    """
    # First, try to get the value directly from environment variable
    env_value = os.environ.get(env_var_name)
    if env_value is not None:
        return env_value
    
    # If not found, try to get from _FILE variant
    file_env_var = f"{env_var_name}_FILE"
    file_path_str = os.environ.get(file_env_var)
    
    if file_path_str:
        try:
            file_path = Path(file_path_str).resolve()
            
            # Security: Validate file path to prevent path traversal
            if not _is_safe_path(file_path):
                core_logger.print_to_log_and_console(
                    f"Unsafe file path detected for {file_env_var}", "error"
                )
                raise EnvironmentError(f"Unsafe file path for {file_env_var}")
            
            # Check if file exists and is readable
            if not file_path.exists():
                core_logger.print_to_log_and_console(
                    f"Secret file not found for {file_env_var}", "error"
                )
                raise EnvironmentError(f"Secret file not found for {file_env_var}")
            
            if not file_path.is_file():
                core_logger.print_to_log_and_console(
                    f"Secret path is not a file for {file_env_var}", "error"
                )
                raise EnvironmentError(f"Secret path is not a file for {file_env_var}")
            
            # Security: Check file permissions (should not be world-readable)
            file_stat = file_path.stat()
            if file_stat.st_mode & stat.S_IROTH:
                core_logger.print_to_log_and_console(
                    f"Secret file is world-readable for {file_env_var}", "warning"
                )
            
            # Security: Limit file size to prevent memory exhaustion (max 64KB for secrets)
            if file_stat.st_size > 65536:  # 64KB
                core_logger.print_to_log_and_console(
                    f"Secret file too large for {file_env_var}", "error"
                )
                raise EnvironmentError(f"Secret file too large for {file_env_var}")
            
            # Read the secret file
            with file_path.open('r', encoding='utf-8') as secret_file:
                content = secret_file.read().strip()
                
                if content:
                    core_logger.print_to_log_and_console(
                        f"Successfully loaded secret from file for {env_var_name}", "debug"
                    )
                    return content
                else:
                    core_logger.print_to_log_and_console(
                        f"Secret file is empty for {file_env_var}", "warning"
                    )
                    
        except (OSError, IOError, UnicodeDecodeError) as e:
            # Log error without exposing file path details
            core_logger.print_to_log_and_console(
                f"Error reading secret file for {file_env_var}: {type(e).__name__}", "error"
            )
            raise EnvironmentError(f"Error reading secret file for {file_env_var}") from e
        except Exception as e:
            core_logger.print_to_log_and_console(
                f"Unexpected error reading secret for {file_env_var}: {type(e).__name__}", "error"
            )
            raise EnvironmentError(f"Unexpected error reading secret for {file_env_var}") from e
    
    # If neither environment variable nor file is found, return default
    return default_value


def _is_safe_path(file_path: Path) -> bool:
    """
    Validate if a file path is safe to access based on allowed locations.
    This function checks if a given file path is within allowed directories,
    primarily focusing on Docker secrets locations and development paths.
    Args:
        file_path (Path): The file path to validate.
    Returns:
        bool: True if the path is safe to access (starts with an allowed prefix
              or is relative to current working directory in development mode),
              False otherwise.
    Note:
        - In production, only specific directories are allowed (Docker secrets paths).
        - In development mode (ENVIRONMENT == "development"), paths relative to the
          current working directory are also considered safe.
        - Returns False if any exception occurs during validation.
    Allowed prefixes:
        - /run/secrets/ (Standard Docker secrets mount point)
        - /var/run/secrets/ (Alternative Docker secrets location)
        - /tmp/ (For testing/development)
        - /secrets/ (Custom secrets directory)
    """
    try:
        path_str = str(file_path)
        
        # Allow common Docker secrets locations
        allowed_prefixes = [
            '/run/secrets/',  # Standard Docker secrets mount point
            '/var/run/secrets/',  # Alternative Docker secrets location
            '/tmp/',  # For testing/development
            '/secrets/',  # Custom secrets directory
        ]
        
        # For development, also allow relative paths in current working directory
        if ENVIRONMENT == "development":
            cwd = Path.cwd()
            try:
                file_path.relative_to(cwd)
                return True
            except ValueError:
                pass
        
        # Check if path starts with any allowed prefix
        return any(path_str.startswith(prefix) for prefix in allowed_prefixes)
        
    except Exception:
        return False


def validate_fernet_key(fernet_key: str | None) -> bool:
    """
    Validates the format and usability of a Fernet encryption key.
    This function checks if the provided Fernet key is valid by attempting to
    create a Fernet cipher instance with it. It performs validation to ensure
    the key is not empty and follows the correct Fernet key format.
    Args:
        fernet_key (str | None): The Fernet encryption key to validate. Should be
            a base64-encoded 32-byte key. Can be None.
    Returns:
        bool: True if the key is valid and can be used to create a Fernet cipher,
            False otherwise.
    Raises:
        None: All exceptions are caught internally and logged. The function returns
            False on any validation failure.
    Notes:
        - Logs validation results using core_logger
        - A valid Fernet key must be a 32-byte key encoded in base64 (URL-safe)
        - Empty or None keys are considered invalid
    """
    if not fernet_key:
        core_logger.print_to_log_and_console(
            "FERNET_KEY is not set or empty", "error"
        )
        return False
    
    try:
        # Attempt to create a Fernet cipher with the key
        fernet_key_bytes = fernet_key.encode('utf-8')
        Fernet(fernet_key_bytes)
        
        core_logger.print_to_log_and_console(
            "FERNET_KEY validation successful", "debug"
        )
        return True
    except ValueError as e:
        core_logger.print_to_log_and_console(
            f"FERNET_KEY validation failed: Invalid key format - {str(e)}", "error"
        )
        return False
    except Exception as e:
        core_logger.print_to_log_and_console(
            f"FERNET_KEY validation failed: Unexpected error - {str(e)}", "error"
        )
        return False


def check_required_env_vars():
    """
    Validates that all required environment variables are set and properly configured.
    This function checks for three categories of environment variables:
    1. Secret variables: Can be set directly or via _FILE variants (for Docker secrets)
    2. Required non-secret variables: Must be set directly
    3. Optional email variables: Logs info messages if missing
    The function will:
    - Log info messages for missing optional email configuration variables
    - Raise EnvironmentError if any required variable (secret or non-secret) is missing
    - Validate FERNET_KEY format if present and log warnings if invalid
    Environment variables checked:
    - Secret vars (direct or _FILE): DB_PASSWORD, SECRET_KEY, FERNET_KEY
    - Required vars: ENDURAIN_HOST
    - Optional email vars: SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD
    Raises:
        EnvironmentError: If any required environment variable is missing or not accessible.
    Note:
        Secret variables support Docker secrets pattern where values can be read from files
        specified by {VAR_NAME}_FILE environment variables.
    """
    # Secrets that support both direct env vars and _FILE variants
    secret_vars = [
        "DB_PASSWORD",
        "SECRET_KEY", 
        "FERNET_KEY"
    ]
    
    # Non-secret required vars that must be set directly
    required_env_vars = [
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

    # Check secret variables - either direct env var or _FILE variant must be present
    for var in secret_vars:
        file_var = f"{var}_FILE"
        if var not in os.environ and file_var not in os.environ:
            core_logger.print_to_log_and_console(
                f"Missing required environment variable: {var} (or {file_var} for Docker secrets)", "error"
            )
            raise EnvironmentError(f"Missing required environment variable: {var} (or {file_var} for Docker secrets)")

    # Check non-secret required variables
    for var in required_env_vars:
        if var not in os.environ:
            core_logger.print_to_log_and_console(
                f"Missing required environment variable: {var}", "error"
            )
            raise EnvironmentError(f"Missing required environment variable: {var}")
    
    # Validate FERNET_KEY if it's available
    fernet_key = read_secret("FERNET_KEY")
    if fernet_key:
        is_valid = validate_fernet_key(fernet_key)
        if not is_valid:
            core_logger.print_to_log_and_console(
                "FERNET_KEY validation failed. Please check the key format and regenerate if necessary.", "warning"
            )
            core_logger.print_to_log_and_console(
                "To generate a new FERNET_KEY, run: python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"", "info"
            )


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
