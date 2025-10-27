"""
File Security Module

A comprehensive file security system for validating uploads and preventing attacks.
"""

# Core classes and configurations
from .config import SecurityLimits, FileSecurityConfig
from .exceptions import (
    ConfigValidationError,
    FileSecurityConfigurationError,
    ErrorCode,
    FileSecurityError,
    FileValidationError,
    FilenameSecurityError,
    UnicodeSecurityError,
    ExtensionSecurityError,
    WindowsReservedNameError,
    FileSizeError,
    MimeTypeError,
    FileSignatureError,
    CompressionSecurityError,
    ZipBombError,
    ZipContentError,
    FileProcessingError,
)
from .enums import (
    DangerousExtensionCategory,
    CompoundExtensionCategory,
    UnicodeAttackCategory,
    SuspiciousFilePattern,
    ZipThreatCategory,
)

# Main validator
from .file_validator import FileValidator

# Specialized validators
from .validators import (
    BaseValidator,
    UnicodeSecurityValidator,
    ExtensionSecurityValidator,
    WindowsSecurityValidator,
    CompressionSecurityValidator,
)

# Inspectors
from .inspectors import ZipContentInspector

# Perform configuration validation when module is imported
# This ensures configuration issues are caught early during application startup
FileSecurityConfig.validate_and_report(strict=False)

# Export all public APIs
__all__ = [
    # Core configuration
    "SecurityLimits",
    "FileSecurityConfig",
    # Exceptions
    "ConfigValidationError",
    "FileSecurityConfigurationError",
    "ErrorCode",
    "FileSecurityError",
    "FileValidationError",
    "FilenameSecurityError",
    "UnicodeSecurityError",
    "ExtensionSecurityError",
    "WindowsReservedNameError",
    "FileSizeError",
    "MimeTypeError",
    "FileSignatureError",
    "CompressionSecurityError",
    "ZipBombError",
    "ZipContentError",
    "FileProcessingError",
    # Enums
    "DangerousExtensionCategory",
    "CompoundExtensionCategory",
    "UnicodeAttackCategory",
    "SuspiciousFilePattern",
    "ZipThreatCategory",
    # Main validator
    "FileValidator",
    # Specialized validators
    "BaseValidator",
    "UnicodeSecurityValidator",
    "ExtensionSecurityValidator",
    "WindowsSecurityValidator",
    "CompressionSecurityValidator",
    # Inspectors
    "ZipContentInspector",
]
