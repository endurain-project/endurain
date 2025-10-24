"""
File Validator Module

Main validator class that coordinates all file security validations.
"""

import os
import time
import mimetypes
from typing import Set, Tuple

import magic
from fastapi import UploadFile

import core.logger as core_logger
from .config import FileSecurityConfig
from .validators import (
    UnicodeSecurityValidator,
    ExtensionSecurityValidator,
    WindowsSecurityValidator,
    CompressionSecurityValidator,
)
from .inspectors import ZipContentInspector


class FileValidator:

    def __init__(self, config: FileSecurityConfig | None = None):
        """
        Initialize the FileValidator with configuration and specialized validators.

        Args:
            config (FileSecurityConfig | None, optional): Configuration object for file security settings.
                If None, a default FileSecurityConfig instance will be created. Defaults to None.

        Attributes:
            config (FileSecurityConfig): The file security configuration to use.
            unicode_validator (UnicodeSecurityValidator): Validator for Unicode security checks.
            extension_validator (ExtensionSecurityValidator): Validator for file extension checks.
            windows_validator (WindowsSecurityValidator): Validator for Windows-specific security checks.
            compression_validator (CompressionSecurityValidator): Validator for compression-related checks.
            zip_inspector (ZipContentInspector): Inspector for ZIP file contents.
            magic_mime (magic.Magic | None): Magic object for MIME type detection if available.
            magic_available (bool): Flag indicating whether python-magic is available for use.

        Raises:
            Exception: Logs a warning if python-magic initialization fails, but does not raise.
        """
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
        Detect the MIME type of a file from its content and filename.

        This method attempts to determine the MIME type using multiple strategies:
        1. Content-based detection using python-magic library (most reliable)
        2. Filename extension-based detection as a fallback
        3. Default to "application/octet-stream" if detection fails

        Args:
            file_content (bytes): The raw binary content of the file to analyze.
            filename (str): The name of the file, used for extension-based detection.

        Returns:
            str: The detected MIME type (e.g., "image/jpeg", "application/pdf") or
                 "application/octet-stream" if detection fails.

        Note:
            - Content-based detection requires the python-magic library to be available.
            - If magic detection fails, the method logs a warning and falls back to
              filename-based detection.
            - Filename-based detection is less reliable as it only considers the extension.
        """
        detected_mime = None

        # Content-based detection using python-magic (most reliable)
        if self.magic_available:
            try:
                detected_mime = self.magic_mime.from_buffer(file_content)
            except Exception as err:
                core_logger.print_to_log(
                    f"Magic MIME detection failed: {err}", "warning"
                )

        # Fallback to filename-based detection
        if not detected_mime:
            core_logger.print_to_log(
                "Fallback to filename-based MIME detection", "info"
            )
            detected_mime, _ = mimetypes.guess_type(filename)

        return detected_mime or "application/octet-stream"

    def _validate_file_signature(self, file_content: bytes, expected_type: str) -> bool:
        """
        Validate a file's content by checking its magic number (file signature).

        This method examines the first few bytes of a file to determine if they match
        known file signatures for the expected file type. This is a more reliable method
        of file type validation than relying solely on file extensions.

        Args:
            file_content (bytes): The raw bytes content of the file to validate.
            expected_type (str): The expected file type category. Currently supports:
                - "image": Validates JPEG and PNG image formats
                - "zip": Validates ZIP archive formats

        Returns:
            bool: True if the file signature matches one of the expected signatures
                  for the given type, False otherwise. Also returns False if the
                  file content is too short (less than 4 bytes).

        Note:
            This method checks against a predefined set of file signatures:
            - JPEG images: Multiple variants including standard and EXIF
            - PNG images: Standard PNG signature
            - ZIP archives: Multiple ZIP format variants including empty and spanning archives
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
        Sanitize a filename to ensure it is safe for filesystem operations.

        This method performs comprehensive filename sanitization including:
        - Unicode security validation to prevent homograph and other Unicode-based attacks
        - Path traversal prevention by removing path components
        - Removal of null bytes and control characters
        - Replacement of dangerous characters with underscores
        - Validation against Windows reserved names (e.g., CON, PRN, AUX)
        - Extension security validation to prevent compound/double extension attacks
        - Filename length limitation while preserving extensions
        - Ensures resulting filename is not empty or extension-only

        Args:
            filename (str): The original filename to sanitize.

        Returns:
            str: A sanitized filename that is safe for filesystem operations.

        Raises:
            ValueError: If the filename is empty, contains dangerous Unicode sequences,
                        is a Windows reserved name, or has dangerous extensions.

        Note:
            The order of validation steps is intentional and critical for security.
            Unicode validation must occur first to prevent bypassing other checks.
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

    def _validate_filename(self, file: UploadFile) -> Tuple[bool, str] | None:
        """
        Validates and sanitizes the filename of an uploaded file.

        This method performs comprehensive filename validation including checking for
        presence, sanitizing potentially dangerous characters or patterns, and verifying
        the filename remains valid after sanitization. The original file object is
        updated with the sanitized filename if validation succeeds.

        Args:
            file (UploadFile): The uploaded file object whose filename needs validation.
                              The filename attribute will be modified in-place if valid.

        Returns:
            Tuple[bool, str] | None: A tuple containing:
                - bool: True if validation succeeds, False otherwise
                - str: An error message describing why validation failed, or empty if successful
                Returns None implicitly if no validation issues occur (though explicit return
                values are preferred in all code paths).

        Raises:
            ValueError: When dangerous file extensions are detected during sanitization.
            Exception: For unexpected errors during the validation process.

        Note:
            This method modifies the file.filename attribute in-place when sanitization
            is successful. All validation failures are logged and returned as descriptive
            error messages rather than raising exceptions to the caller.
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
    ) -> Tuple[bool, str] | None:
        """
        Validate the file extension against allowed and blocked extensions.

        This method checks if the uploaded file has a valid extension by verifying it against
        a set of allowed extensions and ensuring it's not in the blocked extensions list.

        Args:
            file (UploadFile): The uploaded file object to validate
            allowed_extensions (Set[str]): A set of allowed file extensions (e.g., {'.jpg', '.png'})

        Returns:
            Tuple[bool, str] | None: A tuple containing:
                - bool: False if validation fails
                - str: Error message describing the validation failure
                Returns None implicitly if validation passes

        Raises:
            None

        Note:
            - File extensions are compared in lowercase for case-insensitive matching
            - The method first checks if the extension is in the allowed list
            - Then verifies the extension is not in the globally blocked extensions list
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
    ) -> Tuple[bytes | None, int | None, bool, str]:
        """
        Validates the size of an uploaded file against a maximum allowed size.

        This method reads the file content to determine its actual size and compares it
        against the specified maximum file size. It handles files both with and without
        size metadata.

        Args:
            file (UploadFile): The file to validate, typically from a FastAPI upload.
            max_file_size (int): Maximum allowed file size in bytes.

        Returns:
            Tuple[bytes | None, int | None, bool, str]: A tuple containing:
                - bytes | None: The first 8KB of file content if validation passes, None otherwise.
                - int | None: The total file size in bytes if validation passes, None otherwise.
                - bool: True if validation passes, False otherwise.
                - str: A message describing the validation result. Returns "Passed" on success,
                       or an error message indicating why validation failed.

        Note:
            The file pointer is reset to the beginning after size determination.
            This method checks for both oversized files and empty files.
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
        Validates an uploaded image file through multiple security checks.

        This method performs comprehensive validation of an image file including:
        - Filename validation (safe characters, length)
        - File extension validation against allowed image extensions
        - File size validation against configured maximum image size
        - MIME type detection and validation
        - File signature validation to ensure content matches expected image format

        Args:
            file (UploadFile): The uploaded file object to validate.

        Returns:
            Tuple[bool, str]: A tuple containing:
                - bool: True if validation passed, False otherwise
                - str: A message describing the validation result or error

        Raises:
            Exception: Any unexpected errors during validation are caught and logged,
                       returning (False, "File validation failed due to internal error")

        Example:
            >>> validator = FileValidator()
            >>> is_valid, message = await validator.validate_image_file(uploaded_file)
            >>> if is_valid:
            ...     print("Image is valid")
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
        Validates an uploaded ZIP file through multiple security checks.
        This method performs comprehensive validation of ZIP files including:
        - Filename validation for dangerous patterns
        - File extension verification
        - File size limits enforcement
        - MIME type detection and validation
        - ZIP file signature verification
        - Compression ratio analysis (zip bomb detection)
        - ZIP content inspection (if enabled)
        Args:
            file (UploadFile): The uploaded file to validate. Must be a ZIP file.
        Returns:
            Tuple[bool, str]: A tuple containing:
                - bool: True if validation passed, False otherwise
                - str: Success message or detailed error message explaining the validation failure
        Raises:
            ValueError: When a dangerous file extension is detected during validation
            Exception: For any unexpected errors during the validation process
        Notes:
            - The method allows application/octet-stream MIME type if the ZIP signature is valid
            - Full file content is read for compression ratio and content inspection
            - File position is reset to beginning after validation for subsequent operations
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

            # Detect MIME type using first 8KB
            filename = file.filename or "unknown"
            detected_mime = self._detect_mime_type(size_validation[0], filename)

            # Validate ZIP file signature first (most reliable check)
            has_zip_signature = self._validate_file_signature(size_validation[0], "zip")

            if not has_zip_signature:
                return False, "File content does not match ZIP format"

            # Check MIME type, but allow application/octet-stream if signature is valid
            # Some ZIP files are detected as octet-stream, but signature check ensures it's really a ZIP
            if detected_mime not in self.config.ALLOWED_ZIP_MIMES:
                if detected_mime == "application/octet-stream" and has_zip_signature:
                    # Valid ZIP file, just detected as generic binary
                    core_logger.print_to_log(
                        f"ZIP file detected as application/octet-stream, but signature is valid: {filename}",
                        "debug",
                    )
                else:
                    return (
                        False,
                        f"Invalid file type. Detected: {detected_mime}. Expected ZIP file.",
                    )

            # For ZIP validation (compression ratio and content inspection), we need the full file
            # Read the entire file content for proper ZIP analysis
            await file.seek(0)
            full_file_content = await file.read()
            file_size = len(full_file_content)

            # Reset file position for any subsequent operations
            await file.seek(0)

            # Validate ZIP compression ratio to detect zip bombs
            if file_size is not None:
                compression_validation = (
                    self.compression_validator.validate_zip_compression_ratio(
                        full_file_content, file_size
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
                    full_file_content
                )
                if not content_inspection[0]:
                    return (
                        False,
                        f"ZIP content inspection failed: {content_inspection[1]}",
                    )

            core_logger.print_to_log(
                f"ZIP file validation passed: {filename} ({detected_mime}, {file_size} bytes)",
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
