from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base import BaseValidator
from ..exceptions import ExtensionSecurityError, ErrorCode

if TYPE_CHECKING:
    from ..config import FileSecurityConfig


logger = logging.getLogger(__name__)


class ExtensionSecurityValidator(BaseValidator):
    """
    Validates filenames against configured forbidden extensions.

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

    def validate_extensions(self, filename: str) -> None:
        """
        Validate filename against blocked extensions.

        Args:
            filename: Name of the file to validate.

        Raises:
            ExtensionSecurityError: If blocked compound or single
                extension detected in filename.
        """
        # Check for compound dangerous extensions first (e.g., .tar.xz, .user.js)
        filename_lower = filename.lower()
        for compound_ext in self.config.COMPOUND_BLOCKED_EXTENSIONS:
            if filename_lower.endswith(compound_ext):
                logger.warning(
                    "Dangerous compound extension detected",
                    extra={
                        "error_type": "compound_extension_blocked",
                        "file_name": filename,
                        "extension": compound_ext,
                    },
                )
                raise ExtensionSecurityError(
                    message=f"Dangerous compound file extension '{compound_ext}' detected in filename. "
                    f"Upload rejected for security.",
                    filename=filename,
                    extension=compound_ext,
                    error_code=ErrorCode.COMPOUND_EXTENSION_BLOCKED,
                )

        # Check ALL extensions in the filename for dangerous ones
        parts = filename.split(".")
        if len(parts) > 1:
            for i in range(1, len(parts)):
                ext = f".{parts[i].lower()}"
                if ext in self.config.BLOCKED_EXTENSIONS:
                    logger.warning(
                        "Dangerous extension detected",
                        extra={
                            "error_type": "extension_blocked",
                            "file_name": filename,
                            "extension": ext,
                        },
                    )
                    raise ExtensionSecurityError(
                        message=f"Dangerous file extension '{ext}' detected in filename. "
                        f"Upload rejected for security.",
                        filename=filename,
                        extension=ext,
                        error_code=ErrorCode.EXTENSION_BLOCKED,
                    )

    def validate(self, filename: str) -> None:
        """
        Validate the given filename.

        Args:
            filename: Name of the file to validate.

        Raises:
            ExtensionSecurityError: If filename extension is not
                permitted.
        """
        return self.validate_extensions(filename)
