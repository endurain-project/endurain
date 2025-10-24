"""
File Security Utilities Module

Contains utility functions for file security operations.
"""

from fastapi import HTTPException, status, UploadFile

import core.logger as core_logger
from .file_validator import FileValidator
from .config import FileSecurityConfig


# Global validator instance
file_validator = FileValidator()


async def validate_profile_image_upload(file: UploadFile) -> None:
    """
    Validate a profile image file upload.

    This function validates an uploaded image file to ensure it meets the required
    criteria for a profile image. If validation fails, it logs a warning and raises
    an HTTP 400 Bad Request exception.

    Args:
        file (UploadFile): The uploaded file to validate.

    Raises:
        HTTPException: If the image file is invalid, raises a 400 Bad Request error
                       with details about the validation failure.

    Returns:
        None
    """
    is_valid, error_message = await file_validator.validate_image_file(file)

    if not is_valid:
        core_logger.print_to_log(
            f"Profile image upload validation failed: {error_message}", "warning"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image file: {error_message}",
        )


async def validate_profile_data_upload(file: UploadFile) -> None:
    """
    Validates a profile data upload file.

    This function checks if the uploaded file is a valid ZIP file by delegating
    validation to the file_validator. If validation fails, it logs a warning
    and raises an HTTP 400 Bad Request exception.

    Args:
        file (UploadFile): The uploaded file to validate. Must be a ZIP file.

    Raises:
        HTTPException: If the file validation fails, raises a 400 Bad Request
                       exception with details about why the validation failed.

    Returns:
        None: This function doesn't return a value but raises an exception
              if validation fails.
    """
    is_valid, error_message = await file_validator.validate_zip_file(file)

    if not is_valid:
        core_logger.print_to_log(
            f"Profile data upload validation failed: {error_message}", "warning"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ZIP file: {error_message}",
        )


def get_secure_filename(original_filename: str) -> str:
    """
    Sanitize and secure a filename for safe storage.

    This function takes an original filename and sanitizes it to prevent security
    vulnerabilities such as path traversal attacks and invalid characters.

    Args:
        original_filename (str): The original filename to be sanitized.

    Returns:
        str: A sanitized version of the filename that is safe to use.

    Raises:
        ValueError: If the filename cannot be sanitized (re-raised from validator).
        HTTPException: If an unexpected error occurs during sanitization, returns
            a 500 Internal Server Error.

    Example:
        >>> get_secure_filename("../../etc/passwd")
        'passwd'
        >>> get_secure_filename("my_file.txt")
        'my_file.txt'
    """
    try:
        return file_validator._sanitize_filename(original_filename)
    except ValueError as err:
        raise err
    except Exception as err:
        core_logger.print_to_log(
            f"Error during filename sanitization: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error during filename sanitization",
        ) from err


def validate_configuration(strict: bool = False) -> None:
    """
    Validate the file security configuration and log the results.

    This function validates the file security configuration using FileSecurityConfig's
    validate_and_report method. It logs the outcome of the validation, indicating
    success or any issues encountered during the process.

    Args:
        strict (bool, optional): If True, enforces strict validation rules.
            Defaults to False.

    Returns:
        None

    Raises:
        None: All exceptions are caught and logged as warnings rather than
            being propagated.

    Note:
        - Successful validation is logged at 'info' level
        - Validation errors are logged at 'warning' level
    """
    try:
        FileSecurityConfig.validate_and_report(strict=strict)
        core_logger.print_to_log(
            "File security configuration validation completed successfully", "info"
        )
    except Exception as validation_error:
        core_logger.print_to_log(
            f"File security configuration validation encountered issues: {validation_error}",
            "warning",
        )
