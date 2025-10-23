"""
File Validator Module

Main validator class that coordinates all file security validations.
"""
import os
import time
import mimetypes
from typing import Set, Tuple, Optional

import magic
from fastapi import UploadFile

import core.logger as core_logger
from .config import FileSecurityConfig
from .validators import (
    UnicodeSecurityValidator,
    ExtensionSecurityValidator,
    WindowsSecurityValidator,
    CompressionSecurityValidator
)
from .inspectors import ZipContentInspector


class FileValidator:
    """Main file validator that coordinates all security validations."""

    def __init__(self, config: Optional[FileSecurityConfig] = None):
        self.config = config or FileSecurityConfig()

        # Initialize specialized validators
        self.unicode_validator = UnicodeSecurityValidator(self.config)
        self.extension_validator = ExtensionSecurityValidator(self.config)
        self.windows_validator = WindowsSecurityValidator(self.config)
        self.compression_validator = CompressionSecurityValidator(self.config)
        self.zip_inspector = ZipContentInspector(self.config)

        # Initialize python-magic for content-based detection
        try:
            self.magic_mime = magic.Magic(mime=True)
            self.magic_available = True
            core_logger.print_to_log(
                "File content detection (python-magic) initialized", "debug"
            )
        except Exception as err:
            self.magic_available = False
            core_logger.print_to_log(
                f"Warning: python-magic not available for content detection: {err}",
                "warning",
            )

    def _detect_mime_type(self, file_content: bytes, filename: str) -> str:
        """
        Detect MIME type from file content and filename.
        
        Args:
            file_content: The file content as bytes
            filename: The filename
            
        Returns:
            str: The detected MIME type
        """
        detected_mime = None

        # Method 1: Content-based detection using python-magic (most reliable)
        if self.magic_available:
            try:
                detected_mime = self.magic_mime.from_buffer(file_content)
            except Exception as err:
                core_logger.print_to_log(
                    f"Magic MIME detection failed: {err}", "warning"
                )

        # Method 2: Fallback to filename-based detection
        if not detected_mime:
            detected_mime, _ = mimetypes.guess_type(filename)

        return detected_mime or "application/octet-stream"

    def _validate_file_signature(self, file_content: bytes, expected_type: str) -> bool:
        """
        Validate file content matches expected file signatures.
        
        Args:
            file_content: The file content as bytes
            expected_type: The expected file type ("image" or "zip")
            
        Returns:
            bool: True if signature matches expected type
        """
        if len(file_content) < 4:
            return False

        # Common file signatures
        signatures = {
            "image": [
                b"\xff\xd8\xff",  # JPEG
                b"\xff\xd8\xff\xe1",  # JPEG EXIF (additional JPEG variant)
                b"\x89PNG\r\n\x1a\n",  # PNG
            ],
            "zip": [
                b"PK\x03\x04",  # ZIP file
                b"PK\x05\x06",  # Empty ZIP
                b"PK\x07\x08",  # ZIP with spanning
            ],
        }

        expected_signatures = signatures.get(expected_type, [])

        for signature in expected_signatures:
            if file_content.startswith(signature):
                return True

        return False

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename to prevent security issues.
        
        Args:
            filename: The original filename
            
        Returns:
            str: The sanitized filename
            
        Raises:
            ValueError: If dangerous patterns are detected
        """
        if not filename:
            raise ValueError("Filename cannot be empty")

        # Unicode security validation (must be first)
        # This detects and blocks Unicode-based attacks before any other processing
        try:
            filename = self.unicode_validator.validate_unicode_security(filename)
        except ValueError as err:
            raise err

        # Remove path components to prevent directory traversal
        filename = os.path.basename(filename)

        # Remove null bytes and control characters
        filename = "".join(
            char for char in filename if ord(char) >= 32 and char != "\x7f"
        )

        # Remove dangerous characters that could be used for path traversal or command injection
        dangerous_chars = '<>:"/\\|?*\x00'
        for char in dangerous_chars:
            filename = filename.replace(char, "_")

        # Check for Windows reserved names before any other processing
        # This must be done early to prevent reserved names from being created
        self.windows_validator.validate_windows_reserved_names(filename)

        # Handle compound and double extensions security risk
        # This also checks all dangerous extensions
        self.extension_validator.validate_extensions(filename)

        # Limit filename length (preserve extension)
        name_part, ext_part = os.path.splitext(filename)
        if len(name_part) > 100:
            name_part = name_part[:100]
            filename = name_part + ext_part

        # Ensure we don't end up with just an extension or empty name
        if not name_part or name_part.strip() == "":
            filename = f"file_{int(time.time())}{ext_part}"

        # Final check: ensure the sanitized filename doesn't become a reserved name
        self.windows_validator.validate_windows_reserved_names(filename)

        core_logger.print_to_log(
            f"Filename sanitized: original='{os.path.basename(filename if filename else 'None')}' -> sanitized='{filename}'",
            "debug",
        )

        return filename

    def _validate_filename(self, file: UploadFile) -> Optional[Tuple[bool, str]]:
        """
        Validate and sanitize filename.
        
        Args:
            file: The uploaded file
            
        Returns:
            Optional[Tuple[bool, str]]: (is_valid, error_message) or None if valid
        """
        # Check filename
        if not file.filename:
            return False, "Filename is required"

        # Sanitize the filename to prevent security issues
        try:
            sanitized_filename = self._sanitize_filename(file.filename)

            # Update the file object with sanitized filename
            file.filename = sanitized_filename

            # Additional validation after sanitization
            if not sanitized_filename or sanitized_filename.strip() == "":
                return False, "Invalid filename after sanitization"
        except ValueError as err:
            # Dangerous extension detected - reject the file
            return False, str(err)
        except Exception as err:
            core_logger.print_to_log(
                f"Unexpected error during filename validation: {str(err)}", "error"
            )
            return False, "Filename validation failed due to internal error"

    def _validate_file_extension(
        self, file: UploadFile, allowed_extensions: Set[str]
    ) -> Optional[Tuple[bool, str]]:
        """
        Validate file extension against allowed extensions.
        
        Args:
            file: The uploaded file
            allowed_extensions: Set of allowed file extensions
            
        Returns:
            Optional[Tuple[bool, str]]: (is_valid, error_message) or None if valid
        """
        # Check file extension
        if not file.filename:
            return False, "Filename is required for extension validation"

        _, ext = os.path.splitext(file.filename.lower())
        if ext not in allowed_extensions:
            return (
                False,
                f"Invalid file extension. Allowed: {', '.join(allowed_extensions)}",
            )

        # Check for blocked extensions
        if ext in self.config.BLOCKED_EXTENSIONS:
            return False, f"File extension {ext} is blocked for security reasons"

    async def _validate_file_size(
        self, file: UploadFile, max_file_size: int
    ) -> Tuple[Optional[bytes], Optional[int], bool, str]:
        """
        Validate file size and read content.
        
        Args:
            file: The uploaded file
            max_file_size: Maximum allowed file size
            
        Returns:
            Tuple[Optional[bytes], Optional[int], bool, str]: (content, size, is_valid, message)
        """
        # Read first chunk for content analysis
        file_content = await file.read(8192)  # Read first 8KB

        # Reset file position
        await file.seek(0)

        # Check file size
        file_size = len(file_content)
        if hasattr(file, "size") and file.size:
            file_size = file.size
        else:
            # Estimate size by reading the rest
            remaining = await file.read()
            file_size = len(file_content) + len(remaining)
            await file.seek(0)

        if file_size > max_file_size:
            return (
                None,
                None,
                False,
                f"File too large. File size: {file_size // (1024*1024)}MB, maximum: {max_file_size // (1024*1024)}MB",
            )

        if file_size == 0:
            return None, None, False, "Empty file not allowed"

        return file_content, file_size, True, "Passed"

    async def validate_image_file(self, file: UploadFile) -> Tuple[bool, str]:
        """
        Validate image file for security threats.
        
        Args:
            file: The uploaded image file
            
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        """
        try:
            # Validate filename
            filename_validation = self._validate_filename(file)
            if filename_validation is not None:
                return filename_validation

            # Validate file extension
            extension_validation = self._validate_file_extension(
                file, self.config.ALLOWED_IMAGE_EXTENSIONS
            )
            if extension_validation is not None:
                return extension_validation

            # Validate file size
            size_validation = await self._validate_file_size(
                file, self.config.limits.max_image_size
            )
            if size_validation[0] is None:
                return size_validation[2], size_validation[3]

            # Detect MIME type
            filename = file.filename or "unknown"
            detected_mime = self._detect_mime_type(size_validation[0], filename)

            if detected_mime not in self.config.ALLOWED_IMAGE_MIMES:
                return (
                    False,
                    f"Invalid file type. Detected: {detected_mime}. Allowed: {', '.join(self.config.ALLOWED_IMAGE_MIMES)}",
                )

            # Validate file signature
            if not self._validate_file_signature(size_validation[0], "image"):
                return False, "File content does not match expected image format"

            core_logger.print_to_log(
                f"Image file validation passed: {filename} ({detected_mime}, {size_validation[1]} bytes)",
                "debug",
            )

            return True, "Validation successful"
        except Exception as err:
            core_logger.print_to_log(
                f"Error during image file validation: {err}", "error", exc=err
            )
            return False, "File validation failed due to internal error"

    async def validate_zip_file(self, file: UploadFile) -> Tuple[bool, str]:
        """
        Validate ZIP file for security threats.
        
        Args:
            file: The uploaded ZIP file
            
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        """
        try:
            # Validate filename
            filename_validation = self._validate_filename(file)
            if filename_validation is not None:
                return filename_validation

            # Validate file extension
            extension_validation = self._validate_file_extension(
                file, self.config.ALLOWED_ZIP_EXTENSIONS
            )
            if extension_validation is not None:
                return extension_validation

            # Validate file size
            size_validation = await self._validate_file_size(
                file, self.config.limits.max_zip_size
            )
            if size_validation[0] is None:
                return size_validation[2], size_validation[3]

            # Detect MIME type
            filename = file.filename or "unknown"
            detected_mime = self._detect_mime_type(size_validation[0], filename)

            if detected_mime not in self.config.ALLOWED_ZIP_MIMES:
                return (
                    False,
                    f"Invalid file type. Detected: {detected_mime}. Expected ZIP file.",
                )

            # Validate ZIP file signature
            if not self._validate_file_signature(size_validation[0], "zip"):
                return False, "File content does not match ZIP format"

            # Validate ZIP compression ratio to detect zip bombs
            # size_validation[1] is guaranteed to be int here since size_validation[0] is not None
            file_size = size_validation[1]
            if file_size is not None:
                compression_validation = (
                    self.compression_validator.validate_zip_compression_ratio(
                        size_validation[0], file_size
                    )
                )
                if not compression_validation[0]:
                    return (
                        False,
                        f"ZIP compression validation failed: {compression_validation[1]}",
                    )

            # Perform ZIP content inspection if enabled
            if self.config.limits.scan_zip_content:
                content_inspection = self.zip_inspector.inspect_zip_content(
                    size_validation[0]
                )
                if not content_inspection[0]:
                    return (
                        False,
                        f"ZIP content inspection failed: {content_inspection[1]}",
                    )

            core_logger.print_to_log(
                f"ZIP file validation passed: {filename} ({detected_mime}, {size_validation[1]} bytes)",
                "debug",
            )

            return True, "Validation successful"
        except ValueError as err:
            # Dangerous extension detected - reject the file
            return False, str(err)
        except Exception as err:
            core_logger.print_to_log(
                f"Error during ZIP file validation: {err}", "error", exc=err
            )
            return False, "File validation failed due to internal error"