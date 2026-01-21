"""Profile exception classes for import/export operations.

This module defines custom exceptions for profile operations:
- Export errors: database, filesystem, ZIP, memory, data
- Import errors: validation, format, integrity, timeout, size
- Shared errors: filesystem, memory allocation
- Exception to HTTPException conversion utilities
"""

from fastapi import HTTPException, status


# Base exceptions
class ProfileOperationError(Exception):
    """
    Base exception for all profile operations.
    """

    pass


class ExportError(ProfileOperationError):
    """
    Base exception for export operations.
    """

    pass


class ProfileImportError(ProfileOperationError):
    """
    Base exception for import operations.
    """

    pass


# Export-specific exceptions
class DatabaseConnectionError(ExportError):
    """
    Raised when database connection fails during export.
    """

    pass


class FileSystemError(ProfileOperationError):
    """
    Raised when file system operations fail.
    """

    pass


class ZipCreationError(ExportError):
    """
    Raised when ZIP file creation or writing fails.
    """

    pass


class MemoryAllocationError(ProfileOperationError):
    """
    Raised when memory allocation fails.
    """

    pass


class DataCollectionError(ExportError):
    """
    Raised when data collection from database fails.
    """

    pass


class ExportTimeoutError(ExportError):
    """
    Raised when export operation exceeds time limit.
    """

    pass


# Import-specific exceptions
class ImportValidationError(ProfileImportError):
    """
    Raised when import data fails validation checks.
    """

    pass


class FileFormatError(ProfileImportError):
    """
    Raised when imported file format is invalid or corrupted.
    """

    pass


class DataIntegrityError(ProfileImportError):
    """
    Raised when imported data has integrity issues.
    """

    pass


class ImportTimeoutError(ProfileImportError):
    """
    Raised when import operation exceeds time limit.
    """

    pass


class DiskSpaceError(ProfileImportError):
    """
    Raised when insufficient disk space is available.
    """

    pass


class FileSizeError(ProfileImportError):
    """
    Raised when imported file exceeds size limits.
    """

    pass


class ActivityLimitError(ProfileImportError):
    """
    Raised when import contains too many activities.
    """

    pass


class ZipStructureError(ProfileImportError):
    """
    Raised when ZIP file structure is invalid.
    """

    pass


class JSONParseError(ProfileImportError):
    """
    Raised when JSON data cannot be parsed.
    """

    pass


class SchemaValidationError(ProfileImportError):
    """
    Raised when imported data doesn't match expected schema.
    """

    pass


def handle_import_export_exception(error: Exception, operation: str) -> HTTPException:
    """
    Convert exceptions to appropriate HTTP exceptions.

    Args:
        error: The original exception.
        operation: Description of the operation that failed.

    Returns:
        Appropriate HTTP exception with descriptive message.
    """
    # Export-specific exceptions
    if isinstance(error, DatabaseConnectionError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection failed during {operation}. Please try again later.",
        )

    elif isinstance(error, ZipCreationError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to create export archive during {operation}.",
        )

    elif isinstance(error, DataCollectionError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Data collection failed during {operation}. Some data may be corrupted.",
        )

    elif isinstance(error, ExportTimeoutError):
        return HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail=f"Export operation timed out during {operation}. Please try again.",
        )

    # Import-specific exceptions
    elif isinstance(error, ImportValidationError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Import validation failed during {operation}. {str(error)}",
        )

    elif isinstance(error, FileFormatError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file format during {operation}. {str(error)}",
        )

    elif isinstance(error, DataIntegrityError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Data integrity error during {operation}. {str(error)}",
        )

    elif isinstance(error, ImportTimeoutError):
        return HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail=f"Import operation timed out during {operation}. Please try again.",
        )

    elif isinstance(error, DiskSpaceError):
        return HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=f"Insufficient disk space during {operation}. Please free up space and try again.",
        )

    elif isinstance(error, FileSizeError):
        return HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large during {operation}. {str(error)}",
        )

    elif isinstance(error, ActivityLimitError):
        return HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Too many activities during {operation}. {str(error)}",
        )

    elif isinstance(error, ZipStructureError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ZIP file structure during {operation}. {str(error)}",
        )

    elif isinstance(error, JSONParseError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"JSON parsing error during {operation}. {str(error)}",
        )

    elif isinstance(error, SchemaValidationError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Schema validation error during {operation}. {str(error)}",
        )

    # Shared exceptions
    elif isinstance(error, FileSystemError):
        return HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=f"File system error during {operation}. Server storage may be full.",
        )

    elif isinstance(error, MemoryAllocationError):
        return HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=f"Insufficient memory for {operation}. Please try again or contact support.",
        )

    else:
        # Fallback for unexpected errors
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during {operation}. Please contact support.",
        )
