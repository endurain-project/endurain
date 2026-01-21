"""
Profile module for user profile management and operations.

This module provides functionality for:
- User profile retrieval and updates
- MFA (Multi-Factor Authentication) setup and management
- Profile data export and import (ZIP archives)
- Identity provider linking and management
- Session management

Exports:
    - Schemas: MFARequest, MFASetupRequest, MFASetupResponse,
      MFAStatusResponse
    - MFA Store: MFASecretStore
    - Services: ExportService, ImportService
    - Exceptions: ProfileOperationError, ExportError, ProfileImportError,
      and related exception classes
    - Utils: setup_user_mfa, enable_user_mfa, disable_user_mfa,
      verify_user_mfa, is_mfa_enabled_for_user
"""

from .schema import (
    MFARequest,
    MFASetupRequest,
    MFASetupResponse,
    MFAStatusResponse,
)
from .export_service import ExportService
from .import_service import ImportService
from .mfa_store import MFASecretStore
from .exceptions import (
    ProfileOperationError,
    ProfileImportError,
    ExportError,
    DatabaseConnectionError,
    FileSystemError,
    ZipCreationError,
    MemoryAllocationError,
    DataCollectionError,
    ExportTimeoutError,
    ImportValidationError,
    FileFormatError,
    DataIntegrityError,
    ImportTimeoutError,
    DiskSpaceError,
    FileSizeError,
    ActivityLimitError,
    ZipStructureError,
    JSONParseError,
    SchemaValidationError,
)
from .utils import (
    setup_user_mfa,
    enable_user_mfa,
    disable_user_mfa,
    verify_user_mfa,
    is_mfa_enabled_for_user,
)

__all__ = [
    # Schemas
    "MFARequest",
    "MFASetupRequest",
    "MFASetupResponse",
    "MFAStatusResponse",
    # Services
    "ExportService",
    "ImportService",
    # MFA Store
    "MFASecretStore",
    # Exceptions
    "ProfileOperationError",
    "ProfileImportError",
    "ExportError",
    "DatabaseConnectionError",
    "FileSystemError",
    "ZipCreationError",
    "MemoryAllocationError",
    "DataCollectionError",
    "ExportTimeoutError",
    "ImportValidationError",
    "FileFormatError",
    "DataIntegrityError",
    "ImportTimeoutError",
    "DiskSpaceError",
    "FileSizeError",
    "ActivityLimitError",
    "ZipStructureError",
    "JSONParseError",
    "SchemaValidationError",
    # Utils
    "setup_user_mfa",
    "enable_user_mfa",
    "disable_user_mfa",
    "verify_user_mfa",
    "is_mfa_enabled_for_user",
]
