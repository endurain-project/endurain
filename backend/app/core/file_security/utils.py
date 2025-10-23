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
    Validate profile image upload.
    
    Args:
        file: The uploaded image file
        
    Raises:
        HTTPException: If validation fails
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
    Validate profile data ZIP upload.
    
    Args:
        file: The uploaded ZIP file
        
    Raises:
        HTTPException: If validation fails
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
    Get secure filename by sanitizing the original filename.
    
    Args:
        original_filename: The original filename to sanitize
        
    Returns:
        str: The sanitized filename
        
    Raises:
        HTTPException: If sanitization fails
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
    Validate file security configuration.
    
    Args:
        strict: Whether to use strict validation mode
    """
    try:
        FileSecurityConfig.validate_and_report(strict=strict)
        core_logger.print_to_log("File security configuration validation completed successfully", "info")
    except Exception as validation_error:
        core_logger.print_to_log(
            f"File security configuration validation encountered issues: {validation_error}", 
            "warning"
        )