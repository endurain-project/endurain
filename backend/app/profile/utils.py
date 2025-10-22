import json
import pyotp
import qrcode
import base64
import zipfile
import time
import psutil
from io import BytesIO
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import Type, Any, Dict, TypeVar

import core.cryptography as core_cryptography
import core.logger as core_logger
import profile.schema as profile_schema
import users.user.crud as users_crud
from profile.exceptions import (
    MemoryAllocationError,
)

# Type variable for performance config classes
T_PerformanceConfig = TypeVar("T_PerformanceConfig", bound="BasePerformanceConfig")


class BasePerformanceConfig:
    """
    Base class for performance configuration with common patterns and memory-based optimization.

    This abstract base class provides common configuration patterns for both import and export
    operations, including memory-based tier detection, common parameter validation, and
    standardized auto-configuration patterns.

    Common Attributes:
        batch_size (int): Number of records to process in a single batch
        max_memory_mb (int): Maximum memory usage limit in megabytes
        timeout_seconds (int): Operation timeout in seconds
        chunk_size (int): Size of data chunks for reading/writing
        enable_memory_monitoring (bool): Whether to enable memory monitoring

    Memory Tiers:
        High (>2GB): Optimized settings for high-performance systems
        Medium (>1GB): Balanced settings for typical systems
        Low (≤1GB): Conservative settings for resource-constrained systems
    """

    def __init__(
        self,
        batch_size: int = 1000,
        max_memory_mb: int = 1024,
        timeout_seconds: int = 3600,
        chunk_size: int = 8192,
        enable_memory_monitoring: bool = True,
    ):
        """
        Initialize base performance configuration with common parameters.

        Args:
            batch_size (int): Number of items to process in a single batch. Defaults to 1000.
            max_memory_mb (int): Maximum memory usage limit in megabytes. Defaults to 1024.
            timeout_seconds (int): Maximum time allowed for operations in seconds. Defaults to 3600.
            chunk_size (int): Size of data chunks for I/O operations in bytes. Defaults to 8192.
            enable_memory_monitoring (bool): Whether to enable memory monitoring. Defaults to True.
        """
        self.batch_size = batch_size
        self.max_memory_mb = max_memory_mb
        self.timeout_seconds = timeout_seconds
        self.chunk_size = chunk_size
        self.enable_memory_monitoring = enable_memory_monitoring

    @classmethod
    def _get_tier_configs(cls) -> Dict[str, Dict[str, Any]]:
        """
        Get the tier-based configuration mappings.

        This method should be overridden by subclasses to provide specific
        configuration values for each memory tier.

        Returns:
            Dict[str, Dict[str, Any]]: Mapping of tier names to configuration dictionaries
        """
        raise NotImplementedError("Subclasses must implement _get_tier_configs")

    @classmethod
    def get_auto_config(cls: Type[T_PerformanceConfig]) -> T_PerformanceConfig:
        """
        Get automatic configuration based on available system memory.

        This method uses the centralized memory detection to determine the appropriate
        configuration tier and creates an instance with optimized settings.

        Returns:
            T_PerformanceConfig: A configuration instance of the calling class type optimized
                for the current system's available memory. Falls back to default configuration
                if memory detection fails.

        Example:
            >>> config = SomePerformanceConfig.get_auto_config()
            >>> print(f"Tier: {config.batch_size}")
        """
        try:
            tier, _ = detect_system_memory_tier()
            tier_configs = cls._get_tier_configs()

            if tier in tier_configs:
                config_dict = tier_configs[tier]
                return cls(**config_dict)
            else:
                core_logger.print_to_log(
                    f"Unknown memory tier '{tier}', using default config", "warning"
                )
                return cls()
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to create auto config, using defaults: {err}", "warning"
            )
            return cls()


def generate_totp_secret() -> str:
    """
    Generate a base32-encoded secret suitable for TOTP.

    This function returns a cryptographically secure base32 string, generated via
    pyotp.random_base32(), that can be used as the shared secret when provisioning
    time-based one-time password (TOTP) authenticators (e.g., for 2FA).

    Returns:
        str: A base32-encoded secret key for use with TOTP.

    Notes:
        - Treat the returned secret as sensitive; do not log or expose it.
        - The exact length/entropy is determined by pyotp.random_base32().
    """
    return pyotp.random_base32()


def verify_totp(secret: str, token: str) -> bool:
    """
    Verify a Time-based One-Time Password (TOTP) token against a shared secret.

    Parameters
    ----------
    secret : str
        Shared secret used to initialize the TOTP generator (as expected by pyotp, commonly a base32 string).
    token : str
        One-time password (OTP) provided by the user to validate.

    Returns
    -------
    bool
        True if the token is valid within a tolerance of one time-step (current step ±1), False otherwise.

    Notes
    -----
    This function uses pyotp.TOTP.verify with valid_window=1 to allow for minor clock skew between client and server.
    Ensure the secret and token are provided in the formats expected by pyotp.
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(token, valid_window=1)  # Allow 1 window tolerance


def generate_qr_code(secret: str, username: str, app_name: str = "Endurain") -> str:
    """
    Generate a base64-encoded PNG data URI containing a QR code for a TOTP provisioning URI.
    Parameters:
        secret (str): Base32-encoded secret key used to initialize pyotp.TOTP (the shared TOTP secret).
        username (str): Account name (e.g., an email or username) to include in the provisioning URI and display in authenticator apps.
        app_name (str, optional): Issuer name to include in the provisioning URI (default: "Endurain").
    Returns:
        str: A data URI string of the form "data:image/png;base64,<base64-data>" containing the generated QR code PNG.
             This value can be used directly as the src attribute of an HTML <img> element.
    Raises:
        Any exceptions raised by pyotp, qrcode, or the underlying image library (Pillow) may propagate if inputs are invalid
        or if image generation/encoding fails.
    Notes:
        - Builds an otpauth://totp/... provisioning URI via pyotp.TOTP.provisioning_uri(name=username, issuer_name=app_name).
        - Renders the QR code using qrcode with version=1, error correction level L, box_size=10 and border=4.
        - The image is written to an in-memory buffer and base64-encoded so it can be embedded in web pages without a file.
        - Ensure dependencies are installed: pyotp, qrcode, pillow.
    """
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=username, issuer_name=app_name)

    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(provisioning_uri)
    qr.make(fit=True)

    # Create image
    img = qr.make_image(fill_color="black", back_color="white")

    # Convert to base64
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()

    return f"data:image/png;base64,{img_base64}"


def setup_user_mfa(user_id: int, db: Session) -> profile_schema.MFASetupResponse:
    """
    Prepare a TOTP-based MFA enrollment for a user by generating a new secret and a QR code.

    Parameters
    ----------
    user_id : int
        The primary key of the user to prepare MFA for.
    db : Session
        Database session used to look up the user.

    Returns
    -------
    profile_schema.MFASetupResponse
        A response object containing:
          - secret (str): The generated TOTP secret (typically base32).
          - qr_code (str): A representation of the QR code (format depends on implementation;
            commonly a data URI or base64-encoded PNG) that encodes the provisioning URI.
          - app_name (str): Human-friendly application name (set to "Endurain").

    Raises
    ------
    HTTPException
        404 Not Found: if no user with the provided user_id exists.
        400 Bad Request: if MFA is already enabled for the user.

    Notes
    -----
    - This function only generates and returns the secret and QR code; it does not persist the
      secret to the database or enable MFA on the user's account. The caller should verify a
      one-time TOTP code from the user's authenticator and, upon successful verification,
      securely store the secret and mark MFA as enabled.
    - Secrets and QR codes should be transmitted over secure channels (e.g., TLS) and stored
      encrypted at rest. Treat the generated secret as sensitive data.
    """
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled for this user",
        )

    # Generate new secret
    secret = generate_totp_secret()

    # Generate QR code
    qr_code = generate_qr_code(secret, user.username)

    return profile_schema.MFASetupResponse(
        secret=secret, qr_code=qr_code, app_name="Endurain"
    )


def enable_user_mfa(user_id: int, secret: str, mfa_code: str, db: Session):
    """
    Enable multi-factor authentication (MFA) for a user by validating a TOTP code and storing the encrypted secret.

    This function:
    - Confirms the user exists.
    - Ensures MFA is not already enabled for the user.
    - Verifies the provided TOTP (mfa_code) against the provided secret.
    - Encrypts the secret and updates the user's record to enable MFA.

    Parameters
    ----------
    user_id : int
        The ID of the user for whom MFA should be enabled.
    secret : str
        The plain-text TOTP secret provided by the user (will be encrypted before storage).
    mfa_code : str
        The one-time password generated by the user's authenticator app to prove possession of the secret.
    db : Session
        Database session used to look up and update the user record.

    Raises
    ------
    HTTPException
        - 404 NOT FOUND: "User not found" if no user exists with the given user_id.
        - 400 BAD REQUEST: "MFA is already enabled for this user" if MFA is already active for the user.
        - 400 BAD REQUEST: "Invalid MFA code" if the provided mfa_code does not validate against the secret.

    Returns
    -------
    None
        The function performs side effects (encrypting the secret and updating the user's MFA state) and does not return a value.

    Notes
    -----
    Relies on external helpers: users_crud.get_user_by_id, verify_totp, core_cryptography.encrypt_token_fernet, and users_crud.enable_user_mfa.
    """
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled for this user",
        )

    # Verify the MFA code
    if not verify_totp(secret, mfa_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid MFA code"
        )

    # Encrypt the secret before storing
    encrypted_secret = core_cryptography.encrypt_token_fernet(secret)

    # Check if encryption was successful
    if not encrypted_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to encrypt MFA secret",
        )

    # Update user with MFA enabled and secret
    users_crud.enable_user_mfa(user_id, encrypted_secret, db)


def disable_user_mfa(user_id: int, mfa_code: str, db: Session):
    """
    Disable a user's multi-factor authentication (MFA) after verifying a provided TOTP code.

    This function retrieves the user by ID, ensures MFA is currently enabled, decrypts
    the stored MFA secret, verifies the provided TOTP code, and disables MFA for the user
    via the persistence layer.

    Args:
        user_id (int): ID of the user whose MFA should be disabled.
        mfa_code (str): Time-based one-time password (TOTP) code supplied by the user.
        db (Session): Database session used to load and update the user record.

    Returns:
        None

    Raises:
        HTTPException: If the user is not found (404).
        HTTPException: If MFA is not enabled for the user (400).
        HTTPException: If the provided TOTP code is invalid (400).

    Side effects:
        - Decrypts the user's stored MFA secret and uses it to verify the TOTP code.
        - Calls the users_crud layer to disable MFA for the user; commit behavior depends
          on how the provided db session is managed.

    Security considerations:
        - Treat mfa_code and decrypted secrets as sensitive information; avoid logging them.
        - Ensure the db session and cryptographic utilities are used in a secure context.
    """
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if not user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled for this user",
        )

    # Decrypt the secret
    secret = core_cryptography.decrypt_token_fernet(user.mfa_secret)

    # Check if decryption was successful
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decrypt MFA secret",
        )

    # Verify the MFA code
    if not verify_totp(secret, mfa_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid MFA code"
        )

    # Disable MFA for user
    users_crud.disable_user_mfa(user_id, db)


def verify_user_mfa(user_id: int, mfa_code: str, db: Session) -> bool:
    """
    Verify a user's MFA TOTP code.

    Args:
        user_id (int): ID of the user to verify.
        mfa_code (str): Time-based one-time password (TOTP) code provided by the user.
        db (Session): Database session used to retrieve the user record.

    Returns:
        bool: True if the provided TOTP matches the user's decrypted MFA secret;
        False if MFA is not enabled for the user, no secret is stored, the code is invalid,
        or if any decryption/verification error occurs.

    Raises:
        HTTPException: If no user with the given user_id is found (HTTP 404).

    Notes:
        - The function loads the user from the database, ensures MFA is enabled and a secret exists,
          decrypts the stored secret, and then verifies the provided TOTP against that secret.
        - Any exceptions during decryption or verification are treated as verification failures
          and result in a False return value rather than propagating the error.
    """
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if not user.mfa_enabled or not user.mfa_secret:
        return False

    # Decrypt the secret
    try:
        secret = core_cryptography.decrypt_token_fernet(user.mfa_secret)
        if not secret:
            core_logger.print_to_log("Failed to decrypt MFA secret", "error")
            return False
        return verify_totp(secret, mfa_code)
    except Exception as err:
        core_logger.print_to_log(f"Error in verify_user_mfa: {err}", "error", exc=err)
        return False


def is_mfa_enabled_for_user(user_id: int, db: Session) -> bool:
    """
    Return whether multi-factor authentication (MFA) is enabled for a given user.

    This function looks up the user by ID using the provided database session and
    returns True only if the user exists, the user's `mfa_enabled` flag equals 1,
    and `mfa_secret` is not None.

    Args:
        user_id (int): ID of the user to check.
        db (Session): Database session used to retrieve the user record.

    Returns:
        bool: True if MFA is enabled for the user, False otherwise.

    Notes:
        - The function treats mfa_enabled == 1 as enabled.
        - If the user does not exist, the function returns False.
    """
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        return False
    return bool(user.mfa_enabled == 1 and user.mfa_secret is not None)


# Export utility functions
def sqlalchemy_obj_to_dict(obj):
    """
    Converts a SQLAlchemy model instance into a dictionary mapping column names to their values.

    Args:
        obj: The object to convert. If the object has a __table__ attribute (i.e., is a SQLAlchemy model instance),
             its columns and corresponding values are extracted into a dictionary. Otherwise, the object is returned as is.

    Returns:
        dict: A dictionary representation of the SQLAlchemy model instance if applicable, otherwise the original object.
    """
    if hasattr(obj, "__table__"):
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    return obj


def write_json_to_zip(
    zipf: zipfile.ZipFile, filename: str, data, counts: dict, ensure_ascii: bool = False
):
    """
    Writes JSON-serialized data to a file within a ZIP archive.

    Args:
        zipf (zipfile.ZipFile): The ZIP file object to write into.
        filename (str): The name of the file to create within the ZIP archive.
        data (Any): The data to serialize as JSON and write to the file.
        counts (dict): Dictionary to track counts of exported items.
        ensure_ascii (bool, optional): Whether to escape non-ASCII characters in the output. Defaults to False.

    Notes:
        - If data is falsy (e.g., None, empty), nothing is written.
        - Uses json.dumps with default=str to handle non-serializable objects.
    """
    if data:
        counts[filename.split("/")[-1].replace(".json", "")] = (
            len(data) if isinstance(data, (list, tuple)) else 1
        )
        zipf.writestr(
            filename,
            json.dumps(data, default=str, ensure_ascii=ensure_ascii),
        )


def check_timeout(
    timeout_seconds: int | None,
    start_time: float,
    exception_class: Type[Exception],
    operation_type: str,
) -> None:
    """
    Check if an operation has exceeded the specified timeout and raise the appropriate exception.

    This utility function provides a generic timeout checking mechanism that can be used
    by both import and export services. It calculates the elapsed time and raises the
    specified exception if the timeout has been exceeded.

    Args:
        timeout_seconds (int | None): Maximum time allowed in seconds. If None, no timeout is enforced.
        start_time (float): The time when the operation started (from time.time()).
        exception_class (Type[Exception]): The exception class to raise if timeout is exceeded.
        operation_type (str): Description of the operation type (e.g., "Import", "Export") for error messages.

    Raises:
        exception_class: If the operation exceeds the timeout limit.

    Example:
        >>> import time
        >>> start = time.time()
        >>> check_timeout(10, start, ImportTimeoutError, "Import")  # No exception if within 10 seconds
        >>> check_timeout(1, start - 5, ImportTimeoutError, "Import")  # Raises ImportTimeoutError
    """
    if timeout_seconds and (time.time() - start_time) > timeout_seconds:
        raise exception_class(f"{operation_type} exceeded {timeout_seconds} seconds")


def get_memory_usage_mb(enable_monitoring: bool = True) -> float:
    """
    Get the current memory usage of the process in megabytes.

    This utility function retrieves the Resident Set Size (RSS) memory usage of the current
    process and converts it to megabytes. Memory monitoring can be disabled via parameter.

    Args:
        enable_monitoring (bool): Whether memory monitoring is enabled. Defaults to True.

    Returns:
        float: The memory usage in megabytes (MB). Returns 0.0 if memory monitoring
               is disabled or if an error occurs during measurement.

    Raises:
        No exceptions are raised. Errors are logged as warnings and the method
        returns 0.0 on failure.

    Note:
        - RSS (Resident Set Size) represents the portion of memory occupied by the process
          that is held in RAM
        - Failed memory measurements are logged but do not interrupt execution
    """
    try:
        if not enable_monitoring:
            return 0.0
        process = psutil.Process()
        return process.memory_info().rss / (1024 * 1024)  # Convert to MB
    except Exception as err:
        core_logger.print_to_log(f"Failed to get memory usage: {err}", "warning")
        return 0.0


def check_memory_usage(
    operation: str,
    max_memory_mb: int,
    enable_monitoring: bool = True,
    memory_intensive_operations: list[str] | None = None,
) -> None:
    """
    Check current memory usage and enforce limits.

    This utility function monitors memory consumption during operations with an intelligent approach:
    - Only raises errors if memory usage is extremely high (> limit)
    - Warns at 90% to reduce noise while still providing awareness
    - Takes into account that some operations naturally use more memory

    Args:
        operation (str): Description of the current operation being performed,
            used for logging context.
        max_memory_mb (int): Maximum memory usage limit in megabytes.
        enable_monitoring (bool): Whether memory monitoring is enabled. Defaults to True.
        memory_intensive_operations (list[str] | None): List of operation names that are
            known to be memory-intensive and should have higher thresholds. Defaults to None.

    Raises:
        MemoryAllocationError: If current memory usage exceeds the configured maximum
            memory limit by a significant margin (indicating a real problem).

    Note:
        - Memory monitoring can be disabled via enable_monitoring parameter
        - Warning threshold is set at 90% of max_memory_mb to reduce false positives
        - During data-intensive operations, temporary spikes above limit are expected
    """
    if not enable_monitoring:
        return

    current_memory = get_memory_usage_mb(enable_monitoring)

    # Default memory-intensive operations if none provided
    if memory_intensive_operations is None:
        memory_intensive_operations = [
            "ZIP file loading",
            "activities import",
            "activity components",
            "JSON parsing",
            "activity collection",
            "data collection",
            "ZIP creation",
            "file streaming",
        ]

    is_memory_intensive = any(
        op in operation.lower() for op in memory_intensive_operations
    )

    # Use a higher threshold for memory-intensive operations
    effective_limit = max_memory_mb
    if is_memory_intensive:
        effective_limit = max_memory_mb * 1.5  # Allow 50% more for intensive ops

    if current_memory > effective_limit:
        error_msg = (
            f"Memory usage ({current_memory:.1f}MB) critically exceeded limit "
            f"({max_memory_mb}MB, effective: {effective_limit:.1f}MB) during {operation}"
        )
        core_logger.print_to_log(error_msg, "error")
        raise MemoryAllocationError(error_msg)

    # Warn at 90%
    if current_memory > max_memory_mb * 0.9:
        core_logger.print_to_log(
            f"High memory usage: {current_memory:.1f}MB "
            f"(limit: {max_memory_mb}MB) during {operation}",
            "info",
        )


def initialize_operation_counts(include_user_count: bool = False) -> Dict[str, int]:
    """
    Initialize and return a dictionary with count values for various data entities.

    This utility function creates a dictionary with predefined keys representing different
    data categories (media, activities, gears, user settings, etc.) and initializes
    all their counts to 0. This is typically used to track the number of items
    processed during data import/export operations.

    Args:
        include_user_count (bool): Whether to initialize the user count to 1 instead of 0.
            This is useful for export operations where there's always 1 user being exported.
            Defaults to False.

    Returns:
        Dict[str, int]: A dictionary containing entity names as keys and their
            initial count values. The dictionary includes counts for:
            - media: Media files
            - activity_files: Activity data files
            - activities: Activity records
            - activity_laps: Lap data within activities
            - activity_sets: Exercise sets within activities
            - activity_streams: Activity stream data
            - activity_workout_steps: Workout step records
            - activity_media: Media associated with activities
            - activity_exercise_titles: Exercise title records
            - gears: Gear/equipment items
            - gear_components: Components of gear items
            - health_data: Health-related data records
            - health_targets: Health target settings
            - user_images: User profile images
            - user: User account records (0 for import, 1 for export)
            - user_default_gear: Default gear settings for users
            - user_integrations: Third-party integration settings
            - user_goals: User-defined goals
            - user_privacy_settings: Privacy configuration settings
    """
    return {
        "media": 0,
        "activity_files": 0,
        "activities": 0,
        "activity_laps": 0,
        "activity_sets": 0,
        "activity_streams": 0,
        "activity_workout_steps": 0,
        "activity_media": 0,
        "activity_exercise_titles": 0,
        "gears": 0,
        "gear_components": 0,
        "health_data": 0,
        "health_targets": 0,
        "user_images": 0,
        "user": 1 if include_user_count else 0,
        "user_default_gear": 0,
        "user_integrations": 0,
        "user_goals": 0,
        "user_privacy_settings": 0,
    }


def detect_system_memory_tier() -> tuple[str, int]:
    """
    Detect the system memory tier and return the tier name and available memory.

    This utility function analyzes the system's available memory and categorizes it into
    three performance tiers for optimal configuration selection. It provides a consistent
    memory detection approach for both import and export performance configurations.

    Returns:
        tuple[str, int]: A tuple containing:
            - tier (str): Memory tier classification ("high", "medium", "low")
            - available_mb (int): Available memory in megabytes

    Memory Tiers:
        - "high": > 2048 MB (2GB) available - Optimized settings for maximum performance
        - "medium": > 1024 MB (1GB) available - Balanced settings for typical usage
        - "low": <= 1024 MB available - Conservative settings to prevent memory issues

    Raises:
        Does not raise exceptions directly. Any exceptions during memory detection are
        caught and logged as warnings, after which default values are returned.

    Example:
        >>> tier, available_mb = detect_system_memory_tier()
        >>> print(f"Memory tier: {tier}, Available: {available_mb}MB")
    """
    try:
        memory = psutil.virtual_memory()
        available_mb = memory.available // (1024 * 1024)

        if available_mb > 2048:  # > 2GB available
            return "high", available_mb
        elif available_mb > 1024:  # > 1GB available
            return "medium", available_mb
        else:  # Low memory system
            return "low", available_mb
    except Exception as err:
        core_logger.print_to_log(
            f"Failed to detect system memory, using defaults: {err}", "warning"
        )
        return "medium", 1024  # Default to medium tier with 1GB
