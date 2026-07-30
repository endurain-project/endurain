"""
Profile module for user profile management and operations.

This module provides functionality for:
- User profile retrieval and updates
- MFA (Multi-Factor Authentication) setup and management
- Profile data export and import (ZIP archives)
- Identity provider linking and management
- Session management

Exports:
    - Services: ExportService, ImportService
    - Exceptions: ProfileOperationError, ExportError, ProfileImportError,
      and related exception classes
"""

from .exceptions import (
    ActivityLimitError,
    DatabaseConnectionError,
    DataCollectionError,
    DataIntegrityError,
    DiskSpaceError,
    ExportError,
    ExportTimeoutError,
    FileFormatError,
    FileSizeError,
    FileSystemError,
    ImportTimeoutError,
    ImportValidationError,
    JSONParseError,
    MemoryAllocationError,
    ProfileImportError,
    ProfileOperationError,
    SchemaValidationError,
    ZipCreationError,
    ZipStructureError,
)
from .export_service import ExportService
from .import_service import ImportService

__all__ = [
    "ActivityLimitError",
    "DataCollectionError",
    "DataIntegrityError",
    "DatabaseConnectionError",
    "DiskSpaceError",
    "ExportError",
    # Services
    "ExportService",
    "ExportTimeoutError",
    "FileFormatError",
    "FileSizeError",
    "FileSystemError",
    "ImportService",
    "ImportTimeoutError",
    "ImportValidationError",
    "JSONParseError",
    "MemoryAllocationError",
    "ProfileImportError",
    # Exceptions
    "ProfileOperationError",
    "SchemaValidationError",
    "ZipCreationError",
    "ZipStructureError",
]
