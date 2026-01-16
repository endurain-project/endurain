"""Profile utility functions for MFA and data operations.

This module provides helper functions for:
- TOTP secret generation and verification
- QR code generation for MFA setup
- MFA enable/disable/verify workflows
- SQLAlchemy to dict conversion
- Memory and timeout monitoring
- ZIP file operations
- Performance configuration management
"""

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
from typing import Any, TypeVar

import core.cryptography as core_cryptography
import core.logger as core_logger
import profile.schema as profile_schema
import users.user.crud as users_crud
import auth.password_hasher as auth_password_hasher
import auth.mfa_backup_codes.crud as mfa_backup_codes_crud
import auth.mfa_backup_codes.utils as mfa_backup_codes_utils
from profile.exceptions import (
    MemoryAllocationError,
)

# Type variable for performance config classes
T_PerformanceConfig = TypeVar("T_PerformanceConfig", bound="BasePerformanceConfig")


class BasePerformanceConfig:
    """
    Base configuration for performance settings.

    Attributes:
        batch_size: Number of items to process in a batch.
        max_memory_mb: Maximum memory usage in megabytes.
        timeout_seconds: Operation timeout in seconds.
        chunk_size: Size of data chunks in bytes.
        enable_memory_monitoring: Enable memory monitoring.
    """

    def __init__(
        self,
        batch_size: int = 1000,
        max_memory_mb: int = 1024,
        timeout_seconds: int = 3600,
        chunk_size: int = 8192,
        enable_memory_monitoring: bool = True,
    ):
        self.batch_size = batch_size
        self.max_memory_mb = max_memory_mb
        self.timeout_seconds = timeout_seconds
        self.chunk_size = chunk_size
        self.enable_memory_monitoring = enable_memory_monitoring

    @classmethod
    def _get_tier_configs(cls) -> dict[str, dict[str, Any]]:
        """
        Get configuration tiers for different memory levels.

        Returns:
            Dictionary mapping tier names to config dicts.

        Raises:
            NotImplementedError: Must be implemented by subclass.
        """
        raise NotImplementedError("Subclasses must implement _get_tier_configs")

    @classmethod
    def get_auto_config(cls: type[T_PerformanceConfig]) -> T_PerformanceConfig:
        """
        Create config automatically based on system memory.

        Returns:
            Configuration instance for detected tier.
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
    Generate random TOTP secret for MFA.

    Returns:
        Base32-encoded secret string.
    """
    return pyotp.random_base32()


def verify_totp(secret: str, token: str) -> bool:
    """
    Verify TOTP token against secret.

    Args:
        secret: Base32-encoded TOTP secret.
        token: TOTP token to verify.

    Returns:
        True if token is valid, False otherwise.
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(token, valid_window=1)  # Allow 1 window tolerance


def generate_qr_code(secret: str, username: str, app_name: str = "Endurain") -> str:
    """
    Generate QR code for MFA setup.

    Args:
        secret: TOTP secret.
        username: User's username.
        app_name: Application name for MFA.

    Returns:
        Base64-encoded PNG QR code as data URI.
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
    Setup MFA for user.

    Args:
        user_id: User ID to setup MFA for.
        db: Database session.

    Returns:
        MFA setup response with secret and QR code.

    Raises:
        HTTPException: If user not found or MFA enabled.
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


def enable_user_mfa(
    user_id: int,
    secret: str,
    mfa_code: str,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
) -> list[str]:
    """
    Enable MFA for user after verification.

    Args:
        user_id: User ID to enable MFA for.
        secret: TOTP secret to verify.
        mfa_code: MFA code to verify.
        password_hasher: Password hasher instance for backup code generation.
        db: Database session.

    Returns:
        List of generated backup codes.

    Raises:
        HTTPException: If user not found, MFA enabled, code
            invalid, or encryption fails.
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
    users_crud.update_user_mfa(user_id, db, encrypted_secret=encrypted_secret)

    backup_codes = mfa_backup_codes_crud.create_backup_codes(
        user_id, password_hasher, db
    )

    return backup_codes


def disable_user_mfa(user_id: int, mfa_code: str, db: Session) -> None:
    """
    Disable MFA for user after verification.

    Args:
        user_id: User ID to disable MFA for.
        mfa_code: MFA code to verify.
        db: Database session.

    Raises:
        HTTPException: If user not found, MFA not enabled, code
            invalid, or decryption fails.
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
    users_crud.update_user_mfa(user_id, db)

    # Delete all backup codes for user
    mfa_backup_codes_crud.delete_user_backup_codes(user_id, db)


def verify_user_mfa(
    user_id: int,
    mfa_code: str,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
) -> bool:
    """
    Verify MFA code for user (TOTP or backup code).

    Args:
        user_id: User ID to verify MFA for.
        mfa_code: MFA code to verify (6-digit TOTP or 8-character backup code).
        password_hasher: Password hasher instance for backup code verification.
        db: Database session.

    Returns:
        True if code is valid, False otherwise.

    Raises:
        HTTPException: If user not found.

    Notes:
        - First tries TOTP verification (6 digits)
        - If TOTP fails and code is 8 characters, tries backup code
        - Backup codes are consumed on successful verification
    """
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if not user.mfa_enabled or not user.mfa_secret:
        return False

    # Normalize code (remove whitespaces in the beginning and end, uppercase)
    normalized_code = mfa_code.strip().upper()

    # Try TOTP first (6 digits)
    if len(normalized_code) == 6 and normalized_code.isdigit():
        try:
            secret = core_cryptography.decrypt_token_fernet(user.mfa_secret)
            if not secret:
                core_logger.print_to_log("Failed to decrypt MFA secret", "error")
                return False

            if verify_totp(secret, normalized_code):
                core_logger.print_to_log(
                    f"User {user_id} verified MFA with TOTP", "info"
                )
                return True
        except (ValueError, pyotp.OTPError) as err:
            core_logger.print_to_log(
                f"Error in TOTP verification: {err}", "error", exc=err
            )
            return False
        except Exception as err:
            core_logger.print_to_log(
                f"Unknown error in TOTP verification: {err}", "error", exc=err
            )
            return False

    # Try backup code (9 alphanumeric characters with dash XXXX-XXXX)
    elif len(normalized_code) == 9 and normalized_code[4] == "-":
        try:
            if mfa_backup_codes_utils.verify_and_consume_backup_code(
                user_id, normalized_code, password_hasher, db
            ):
                return True
        except Exception as err:
            core_logger.print_to_log(
                f"Error in backup code verification: {err}", "error", exc=err
            )
            return False

    # Invalid format or code didn't match
    return False


def is_mfa_enabled_for_user(user_id: int, db: Session) -> bool:
    """
    Check if MFA is enabled for user.

    Args:
        user_id: User ID to check.
        db: Database session.

    Returns:
        True if MFA is enabled, False otherwise.
    """
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        return False
    return bool(user.mfa_enabled == 1 and user.mfa_secret is not None)


# Export utility functions
def sqlalchemy_obj_to_dict(obj: Any) -> dict[str, Any]:
    """
    Convert SQLAlchemy object to dictionary.

    Args:
        obj: SQLAlchemy model instance or other object.

    Returns:
        Dictionary with column names and values.
    """
    if hasattr(obj, "__table__"):
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    return obj


def write_json_to_zip(
    zipf: zipfile.ZipFile,
    filename: str,
    data: dict,
    counts: dict,
    ensure_ascii: bool = False,
) -> None:
    """
    Write JSON data to ZIP file and update counts.

    Args:
        zipf: ZipFile instance to write to.
        filename: Name of file in ZIP.
        data: Data to serialize as JSON.
        counts: Dictionary to update with item counts.
        ensure_ascii: Whether to ensure ASCII encoding.
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
    exception_class: type[Exception],
    operation_type: str,
) -> None:
    """
    Check if operation has exceeded timeout.

    Args:
        timeout_seconds: Timeout limit in seconds or None.
        start_time: Operation start time from time.time().
        exception_class: Exception type to raise on timeout.
        operation_type: Description of operation for error.

    Raises:
        exception_class: If timeout is exceeded.
    """
    if timeout_seconds and (time.time() - start_time) > timeout_seconds:
        raise exception_class(f"{operation_type} exceeded {timeout_seconds} seconds")


def get_memory_usage_mb(enable_monitoring: bool = True) -> float:
    """
    Get current process memory usage in megabytes.

    Args:
        enable_monitoring: Whether monitoring is enabled.

    Returns:
        Memory usage in MB, or 0.0 if disabled or error.
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
    Check memory usage and raise error if limit exceeded.

    Args:
        operation: Description of current operation.
        max_memory_mb: Maximum allowed memory in MB.
        enable_monitoring: Whether monitoring is enabled.
        memory_intensive_operations: List of intensive ops.

    Raises:
        MemoryAllocationError: If memory limit exceeded.
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


def initialize_operation_counts(include_user_count: bool = False) -> dict[str, int]:
    """
    Initialize dictionary for tracking operation counts.

    Args:
        include_user_count: Whether to include user count.

    Returns:
        Dictionary with all count keys initialized to 0.
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
        "health_weight": 0,
        "health_targets": 0,
        "notifications": 0,
        "user_images": 0,
        "user": 1 if include_user_count else 0,
        "user_default_gear": 0,
        "user_goals": 0,
        "user_identity_providers": 0,
        "user_integrations": 0,
        "user_privacy_settings": 0,
    }


def detect_system_memory_tier() -> tuple[str, int]:
    """
    Detect system memory tier based on available memory.

    Returns:
        Tuple of tier name and available memory in MB.
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
