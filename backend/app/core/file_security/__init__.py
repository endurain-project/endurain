"""
File Security Module

A comprehensive file security system for validating uploads and preventing attacks.

This module provides backward compatibility with the original file_security.py API
while implementing a modular, maintainable architecture.
"""

# Core classes and configurations
from .config import SecurityLimits, FileSecurityConfig
from .exceptions import ConfigValidationError, FileSecurityConfigurationError
from .enums import (
    DangerousExtensionCategory,
    CompoundExtensionCategory,
    UnicodeAttackCategory,
    SuspiciousFilePattern,
    ZipThreatCategory
)

# Main validator
from .file_validator import FileValidator

# Specialized validators
from .validators import (
    BaseValidator,
    UnicodeSecurityValidator,
    ExtensionSecurityValidator,
    WindowsSecurityValidator,
    CompressionSecurityValidator
)

# Inspectors
from .inspectors import ZipContentInspector

# Utility functions (for backward compatibility)
from .utils import (
    validate_profile_image_upload,
    validate_profile_data_upload,
    get_secure_filename,
    validate_configuration,
    file_validator
)

# Perform configuration validation when module is imported
# This ensures configuration issues are caught early during application startup
validate_configuration(strict=False)

# Export all public APIs for backward compatibility
__all__ = [
    # Core configuration
    "SecurityLimits",
    "FileSecurityConfig",
    
    # Exceptions
    "ConfigValidationError", 
    "FileSecurityConfigurationError",
    
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
    
    # Utility functions (maintain original API)
    "validate_profile_image_upload",
    "validate_profile_data_upload",
    "get_secure_filename",
    "validate_configuration",
    "file_validator"
]