"""
Custom exceptions for profile export operations.

This module defines specific exception types to provide better error handling
and more informative error messages for different failure scenarios.
"""

from fastapi import HTTPException, status


class ExportError(Exception):
    """Base exception for export operations."""
    pass


class DatabaseConnectionError(ExportError):
    """Raised when database connection fails during export."""
    pass


class FileSystemError(ExportError):
    """Raised when file system operations fail during export."""
    pass


class ZipCreationError(ExportError):
    """Raised when ZIP file creation or writing fails."""
    pass


class MemoryAllocationError(ExportError):
    """Raised when memory allocation fails during export."""
    pass


class DataCollectionError(ExportError):
    """Raised when data collection from database fails."""
    pass


class ExportTimeoutError(ExportError):
    """Raised when export operation exceeds time limit."""
    pass


def handle_export_exception(error: Exception, operation: str) -> HTTPException:
    """
    Convert export-specific exceptions to appropriate HTTP exceptions.
    
    Args:
        error (Exception): The original exception
        operation (str): Description of the operation that failed
        
    Returns:
        HTTPException: Appropriate HTTP exception with descriptive message
    """
    if isinstance(error, DatabaseConnectionError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection failed during {operation}. Please try again later."
        )
    
    elif isinstance(error, FileSystemError):
        return HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=f"File system error during {operation}. Server storage may be full."
        )
    
    elif isinstance(error, ZipCreationError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to create export archive during {operation}."
        )
    
    elif isinstance(error, MemoryAllocationError):
        return HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=f"Insufficient memory for {operation}. Please try again or contact support."
        )
    
    elif isinstance(error, DataCollectionError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Data collection failed during {operation}. Some data may be corrupted."
        )
    
    elif isinstance(error, ExportTimeoutError):
        return HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail=f"Export operation timed out during {operation}. Please try again."
        )
    
    else:
        # Fallback for unexpected errors
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during {operation}. Please contact support."
        )