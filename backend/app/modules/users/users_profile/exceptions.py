"""Profile exception classes for import/export operations.

This module defines custom exceptions for profile operations:
- Export errors: database, filesystem, ZIP, memory, data
- Import errors: validation, format, integrity, timeout, size
- Shared errors: filesystem, memory allocation
- Conversion of these exceptions to ``core.exceptions`` errors
"""

from http import HTTPStatus

from sqlalchemy.exc import SQLAlchemyError

import core.exceptions as core_exceptions


# Base exceptions
class ProfileOperationError(Exception):
    """Base exception for all profile operations."""

    pass


class ExportError(ProfileOperationError):
    """Base exception for export operations."""

    pass


class ProfileImportError(ProfileOperationError):
    """Base exception for import operations."""

    pass


# Export-specific exceptions
class DatabaseConnectionError(ExportError):
    """Raised when database connection fails during export."""

    pass


class FileSystemError(ProfileOperationError):
    """Raised when file system operations fail."""

    pass


class ZipCreationError(ExportError):
    """Raised when ZIP file creation or writing fails."""

    pass


class MemoryAllocationError(ProfileOperationError):
    """Raised when memory allocation fails."""

    pass


class DataCollectionError(ExportError):
    """Raised when data collection from database fails."""

    pass


class ExportTimeoutError(ExportError):
    """Raised when export operation exceeds time limit."""

    pass


# Import-specific exceptions
class ImportValidationError(ProfileImportError):
    """Raised when import data fails validation checks."""

    pass


class FileFormatError(ProfileImportError):
    """Raised when imported file format is invalid or corrupted."""

    pass


class DataIntegrityError(ProfileImportError):
    """Raised when imported data has integrity issues."""

    pass


class ImportTimeoutError(ProfileImportError):
    """Raised when import operation exceeds time limit."""

    pass


class DiskSpaceError(ProfileImportError):
    """Raised when insufficient disk space is available."""

    pass


class FileSizeError(ProfileImportError):
    """Raised when imported file exceeds size limits."""

    pass


class ActivityLimitError(ProfileImportError):
    """Raised when import contains too many activities."""

    pass


class ZipStructureError(ProfileImportError):
    """Raised when ZIP file structure is invalid."""

    pass


class JSONParseError(ProfileImportError):
    """Raised when JSON data cannot be parsed."""

    pass


class SchemaValidationError(ProfileImportError):
    """Raised when imported data doesn't match expected schema."""

    pass


class TransferTimeoutError(core_exceptions.DomainError):
    """An export or import ran past its time limit."""

    status_code = HTTPStatus.REQUEST_TIMEOUT.value
    code = "transfer-timeout"
    title = "Request Timeout"
    default_detail = "The operation timed out"


class TransferUnprocessableError(core_exceptions.DomainError):
    """An export or import could not be completed with the data it was given."""

    status_code = HTTPStatus.UNPROCESSABLE_CONTENT.value
    code = "transfer-unprocessable"
    title = "Unprocessable Content"
    default_detail = "The data could not be processed"


class InsufficientStorageError(core_exceptions.DomainError):
    """The server ran out of disk space or memory for an export or import."""

    status_code = HTTPStatus.INSUFFICIENT_STORAGE.value
    code = "insufficient-storage"
    title = "Insufficient Storage"
    default_detail = "The server does not have enough storage"


def to_domain_error(error: Exception, operation: str) -> core_exceptions.DomainError:
    """Convert a profile transfer exception to the matching ``core.exceptions`` error.

    Args:
        error: The original exception.
        operation: Description of the operation that failed.

    Returns:
        The domain error carrying a caller-safe message.
    """
    if isinstance(error, DatabaseConnectionError):
        return core_exceptions.ServiceUnavailableError(
            f"Database connection failed during {operation}. Please try again later."
        )
    if isinstance(error, ZipCreationError):
        return TransferUnprocessableError(f"Failed to create export archive during {operation}.")
    if isinstance(error, DataCollectionError):
        return TransferUnprocessableError(f"Data collection failed during {operation}. Some data may be corrupted.")
    if isinstance(error, ExportTimeoutError):
        return TransferTimeoutError(f"Export operation timed out during {operation}. Please try again.")
    if isinstance(error, ImportValidationError):
        return core_exceptions.InvalidInputError(f"Import validation failed during {operation}. {error!s}")
    if isinstance(error, FileFormatError):
        return core_exceptions.InvalidInputError(f"Invalid file format during {operation}. {error!s}")
    if isinstance(error, DataIntegrityError):
        return TransferUnprocessableError(f"Data integrity error during {operation}. {error!s}")
    if isinstance(error, ImportTimeoutError):
        return TransferTimeoutError(f"Import operation timed out during {operation}. Please try again.")
    if isinstance(error, DiskSpaceError):
        return InsufficientStorageError(
            f"Insufficient disk space during {operation}. Please free up space and try again."
        )
    if isinstance(error, FileSizeError):
        return core_exceptions.PayloadTooLargeError(f"File too large during {operation}. {error!s}")
    if isinstance(error, ActivityLimitError):
        return core_exceptions.PayloadTooLargeError(f"Too many activities during {operation}. {error!s}")
    if isinstance(error, ZipStructureError):
        return core_exceptions.InvalidInputError(f"Invalid ZIP file structure during {operation}. {error!s}")
    if isinstance(error, JSONParseError):
        return core_exceptions.InvalidInputError(f"JSON parsing error during {operation}. {error!s}")
    if isinstance(error, SchemaValidationError):
        return core_exceptions.InvalidInputError(f"Schema validation error during {operation}. {error!s}")
    if isinstance(error, FileSystemError):
        return InsufficientStorageError(f"File system error during {operation}. Server storage may be full.")
    if isinstance(error, MemoryAllocationError):
        return InsufficientStorageError(f"Insufficient memory for {operation}. Please try again or contact support.")
    return core_exceptions.ProcessingError(f"Unexpected error during {operation}. Please contact support.")


def is_transient(error: BaseException) -> bool:
    """Whether a failure may pass on its own, so running the job again can succeed.

    A collector wraps the database error it hit in a profile error, so the cause chain is read too.

    Args:
        error: What the import or export raised.

    Returns:
        True for a database, storage or availability failure; the archive's own faults and resource
        limits are final.
    """
    while error is not None:
        if isinstance(error, SQLAlchemyError | OSError | core_exceptions.ServiceUnavailableError):
            return True
        error = error.__cause__
    return False
