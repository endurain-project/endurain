"""Windows security validator for filename validation."""

from __future__ import annotations

import os
import logging
from typing import TYPE_CHECKING

from .base import BaseValidator
from ..exceptions import WindowsReservedNameError

if TYPE_CHECKING:
    from ..config import FileSecurityConfig


logger = logging.getLogger(__name__)


class WindowsSecurityValidator(BaseValidator):
    """
    Validator for Windows reserved device names.

    Attributes:
        config: File security configuration settings.
    """

    def __init__(self, config: FileSecurityConfig):
        """
        Initialize the validator.

        Args:
            config: File security configuration settings.
        """
        super().__init__(config)

    def validate_windows_reserved_names(self, filename: str) -> None:
        """
        Validate filename against Windows reserved device names.

        Args:
            filename: The filename to validate.

        Raises:
            WindowsReservedNameError: If filename matches a Windows
                reserved device name.
        """
        # Check iteratively by removing extensions to handle compound extensions
        # e.g., "CON.tar.gz" -> check "con.tar" and "con"
        current_name = filename

        while current_name:
            # Get basename without extension
            name_without_ext, ext = os.path.splitext(current_name)

            # Normalize: lowercase, strip whitespace
            name_to_check = name_without_ext.lower().strip()
            # Remove leading dots to handle hidden files like ".CON.jpg"
            name_to_check = name_to_check.lstrip(".")
            # Remove trailing dots to handle cases like "con." or "con.."
            name_to_check = name_to_check.rstrip(".")

            if name_to_check in self.config.WINDOWS_RESERVED_NAMES:
                logger.warning(
                    "Windows reserved name detected",
                    extra={
                        "error_type": "windows_reserved_name",
                        "file_name": filename,
                        "reserved_name": name_to_check.upper(),
                    },
                )
                raise WindowsReservedNameError(
                    message=f"Filename '{filename}' uses Windows reserved name '{name_to_check.upper()}'. "
                    f"Reserved names: {', '.join(sorted(self.config.WINDOWS_RESERVED_NAMES)).upper()}",
                    filename=filename,
                    reserved_name=name_to_check.upper(),
                )

            # If no extension was removed, we're done
            if not ext or name_without_ext == current_name:
                break

            current_name = name_without_ext

    def validate(self, filename: str) -> None:
        """
        Validate filename against Windows reserved naming rules.

        Args:
            filename: The filename to validate.

        Raises:
            WindowsReservedNameError: If filename matches a Windows
                reserved device name.
        """
        return self.validate_windows_reserved_names(filename)
