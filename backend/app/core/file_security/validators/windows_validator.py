"""
Windows Security Validator Module

Handles validation of Windows-specific security threats.
"""
import os
from typing import TYPE_CHECKING

from .base import BaseValidator

if TYPE_CHECKING:
    from ..config import FileSecurityConfig


class WindowsSecurityValidator(BaseValidator):

    def __init__(self, config: "FileSecurityConfig"):
        super().__init__(config)

    def validate_windows_reserved_names(self, filename: str) -> None:
        """
        Validate that filename doesn't use Windows reserved names.
        
        Args:
            filename: The filename to validate
            
        Raises:
            ValueError: If Windows reserved names are detected
        """
        name_without_ext = os.path.splitext(filename)[0].lower().strip()
        # Remove leading dots to handle hidden files like ".CON.jpg"
        name_without_ext = name_without_ext.lstrip(".")
        # Remove trailing dots to handle cases like "con." or "con.."
        name_without_ext = name_without_ext.rstrip(".")

        if name_without_ext in self.config.WINDOWS_RESERVED_NAMES:
            raise ValueError(
                f"Filename '{filename}' uses Windows reserved name '{name_without_ext.upper()}'. "
                f"Reserved names: {', '.join(sorted(self.config.WINDOWS_RESERVED_NAMES)).upper()}"
            )
    
    def validate(self, filename: str) -> None:
        """Compatibility method for base class interface."""
        return self.validate_windows_reserved_names(filename)