"""
Extension Security Validator Module

Handles validation of file extensions for security threats.
"""
from typing import TYPE_CHECKING

from .base import BaseValidator

if TYPE_CHECKING:
    from ..config import FileSecurityConfig


class ExtensionSecurityValidator(BaseValidator):

    def __init__(self, config: "FileSecurityConfig"):
        super().__init__(config)

    def validate_extensions(self, filename: str) -> None:
        """
        Validate file extensions for security threats.
        
        Args:
            filename: The filename to validate
            
        Raises:
            ValueError: If dangerous extensions are detected
        """
        # Check for compound dangerous extensions first (e.g., .tar.xz, .user.js)
        filename_lower = filename.lower()
        for compound_ext in self.config.COMPOUND_BLOCKED_EXTENSIONS:
            if filename_lower.endswith(compound_ext):
                raise ValueError(
                    f"Dangerous compound file extension '{compound_ext}' detected in filename. Upload rejected for security."
                )

        # Check ALL extensions in the filename for dangerous ones
        parts = filename.split(".")
        if len(parts) > 1:
            for i in range(1, len(parts)):
                if f".{parts[i].lower()}" in self.config.BLOCKED_EXTENSIONS:
                    raise ValueError(
                        f"Dangerous file extension '.{parts[i].lower()}' detected in filename. Upload rejected for security."
                    )
    
    def validate(self, filename: str) -> None:
        """Compatibility method for base class interface."""
        return self.validate_extensions(filename)