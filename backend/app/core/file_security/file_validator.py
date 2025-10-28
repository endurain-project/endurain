"""Main file validator coordinating all security validations."""

import logging
import os
import time
import mimetypes

import magic

# Optional FastAPI integration - fallback to protocol if not available
try:
    from fastapi import UploadFile
except ImportError:
    from .protocols import UploadFileProtocol as UploadFile

from .config import FileSecurityConfig
from .validators import (
    UnicodeSecurityValidator,
    ExtensionSecurityValidator,
    WindowsSecurityValidator,
    CompressionSecurityValidator,
)
from .inspectors import ZipContentInspector
from .exceptions import (
    ErrorCode,
    FileValidationError,
    FilenameSecurityError,
    ExtensionSecurityError,
    FileSizeError,
    MimeTypeError,
    FileSignatureError,
    FileProcessingError,
)


logger = logging.getLogger(__name__)


class FileValidator:
    """
    Coordinated security validation for uploaded files.

    Attributes:
        config: Active security configuration.
        unicode_validator: Validator for Unicode-related checks.
        extension_validator: Validator for file extension rules.
        windows_validator: Validator enforcing Windows-specific constraints.
        compression_validator: Validator handling compressed file limits.
        zip_inspector: Inspector for ZIP archive contents.
        magic_mime: MIME type detector based on python-magic.
        magic_available: Whether python-magic was successfully initialized.
    """

    def __init__(self, config: FileSecurityConfig | None = None):
        """
        Initialize file validator with configuration and detection utilities.

        Args:
            config: Optional configuration object defining file security
                rules. Defaults to new FileSecurityConfig instance.

        Attributes:
            config: Active security configuration.
            unicode_validator: Validator for Unicode-related checks.
            extension_validator: Validator for file extension rules.
            windows_validator: Validator enforcing Windows constraints.
            compression_validator: Validator for compressed file limits.
            zip_inspector: Inspector for ZIP archive contents.
            magic_mime: MIME type detector based on python-magic.
            magic_available: Whether python-magic initialized successfully.
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
            logger.debug("File content detection (python-magic) initialized")
        except Exception as err:
            self.magic_available = False
            logger.warning(
                "python-magic not available for content detection: %s",
                err,
            )

    def _detect_mime_type(self, file_content: bytes, filename: str) -> str:
        """
        Determine MIME type for file content.

        Args:
            file_content: Raw bytes of the file to inspect.
            filename: Original filename for fallback MIME detection.

        Returns:
            Detected MIME type or "application/octet-stream" if detection
            fails.
        """
        detected_mime = None

        # Content-based detection using python-magic (most reliable)
        if self.magic_available:
            try:
                detected_mime = self.magic_mime.from_buffer(file_content)
            except Exception as err:
                logger.warning("Magic MIME detection failed: %s", err)

        # Fallback to filename-based detection
        if not detected_mime:
            logger.info("Fallback to filename-based MIME detection")
            detected_mime, _ = mimetypes.guess_type(filename)

        return detected_mime or "application/octet-stream"

    def _validate_file_signature(self, file_content: bytes, expected_type: str) -> None:
        """
        Verify file content begins with known signature for expected type.

        Args:
            file_content: Raw bytes of the uploaded file.
            expected_type: Logical file category ("image" or "zip").

        Raises:
            FileSignatureError: File header doesn't match expected type
                signatures.
        """
        if len(file_content) < 4:
            raise FileSignatureError(
                f"File too small to verify {expected_type} signature",
                expected_type=expected_type,
            )

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
                return  # Signature matched

        # No matching signature found
        raise FileSignatureError(
            f"File content does not match expected {expected_type} format",
            expected_type=expected_type,
        )

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize user-provided filename to prevent security risks.

        Args:
            filename: Original filename supplied by the user.

        Returns:
            Sanitized filename safe for storage and processing.

        Raises:
            UnicodeSecurityError: Filename contains dangerous Unicode
                characters or fails normalization checks.
            WindowsReservedNameError: Filename uses Windows reserved
                device names.
            ExtensionSecurityError: Filename contains blocked or
                dangerous file extensions.
            ValueError: Filename is empty string.
        """
        if not filename:
            raise ValueError("Filename cannot be empty")

        # Unicode security validation (must be first)
        # This detects and blocks Unicode-based attacks before any other processing
        filename = self.unicode_validator.validate_unicode_security(filename)

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

        logger.debug(
            "Filename sanitized: original='%s' -> sanitized='%s'",
            os.path.basename(filename if filename else "None"),
            filename,
        )

        return filename

    def _validate_filename(self, file: UploadFile) -> None:
        """
        Validate filename of uploaded file and sanitize it in place.

        Args:
            file: Uploaded file whose filename should be validated and
                sanitized.

        Raises:
            FilenameSecurityError: Filename is empty, invalid, or fails
                sanitization.
            FileProcessingError: Unexpected error during filename
                validation.
        """
        # Check filename
        if not file.filename:
            raise FilenameSecurityError(
                "Filename is required",
                error_code=ErrorCode.FILENAME_EMPTY,
            )

        # Sanitize the filename to prevent security issues
        try:
            sanitized_filename = self._sanitize_filename(file.filename)

            # Update the file object with sanitized filename
            file.filename = sanitized_filename

            # Additional validation after sanitization
            if not sanitized_filename or sanitized_filename.strip() == "":
                raise FilenameSecurityError(
                    "Invalid filename after sanitization",
                    filename=file.filename,
                    error_code=ErrorCode.FILENAME_INVALID,
                )
        except FileValidationError:
            # Let FileValidationError and subclasses propagate
            raise
        except Exception as err:
            logger.exception("Unexpected error during filename validation: %s", err)
            raise FileProcessingError(
                "Filename validation failed due to internal error",
                original_error=err,
            ) from err

    def _validate_file_extension(
        self, file: UploadFile, allowed_extensions: set[str]
    ) -> None:
        """
        Validate extension of uploaded file against allowed and blocked lists.

        Args:
            file: File whose extension will be validated.
            allowed_extensions: Set of allowed file extensions.

        Raises:
            FilenameSecurityError: Filename is missing.
            ExtensionSecurityError: Extension is not allowed or is blocked.
        """
        # Check file extension
        if not file.filename:
            raise FilenameSecurityError(
                "Filename is required for extension validation",
                error_code=ErrorCode.FILENAME_EMPTY,
            )

        _, ext = os.path.splitext(file.filename.lower())
        if ext not in allowed_extensions:
            raise ExtensionSecurityError(
                f"Invalid file extension. Allowed: {', '.join(allowed_extensions)}",
                filename=file.filename,
                extension=ext,
                error_code=ErrorCode.EXTENSION_NOT_ALLOWED,
            )

        # Check for blocked extensions
        if ext in self.config.BLOCKED_EXTENSIONS:
            raise ExtensionSecurityError(
                f"File extension {ext} is blocked for security reasons",
                filename=file.filename,
                extension=ext,
                error_code=ErrorCode.EXTENSION_BLOCKED,
            )

    async def _validate_file_size(
        self, file: UploadFile, max_file_size: int
    ) -> tuple[bytes, int]:
        """
        Validate uploaded file size by sampling content and determining total bytes.

        Args:
            file: Uploaded file supporting asynchronous read and seek.
            max_file_size: Maximum allowed file size in bytes.

        Returns:
            Tuple containing first 8 KB of file content and detected file
            size in bytes.

        Raises:
            FileSizeError: File size exceeds maximum or file is empty.
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
            raise FileSizeError(
                f"File too large. File size: {file_size // (1024*1024)}MB, maximum: {max_file_size // (1024*1024)}MB",
                size=file_size,
                max_size=max_file_size,
            )

        if file_size == 0:
            raise FileSizeError(
                "Empty file not allowed",
                size=0,
                max_size=max_file_size,
            )

        return file_content, file_size

    async def validate_image_file(self, file: UploadFile) -> None:
        """
        Validate uploaded image by checking filename, extension, size, MIME type, and signature.

        Args:
            file: Uploaded file to validate.

        Raises:
            FilenameSecurityError: Filename is empty, invalid, or fails
                security checks.
            ExtensionSecurityError: File extension is not allowed or is
                blocked.
            FileSizeError: File size exceeds maximum or file is empty.
            MimeTypeError: MIME type is not in allowed image types.
            FileSignatureError: File signature doesn't match expected image
                format.
            FileProcessingError: Unexpected error during validation.
        """
        try:
            # Validate filename (raises exceptions on failure)
            self._validate_filename(file)

            # Validate file extension (raises exceptions on failure)
            self._validate_file_extension(file, self.config.ALLOWED_IMAGE_EXTENSIONS)

            # Validate file size (raises exceptions on failure, returns content and size on success)
            file_content, file_size = await self._validate_file_size(
                file, self.config.limits.max_image_size
            )

            # Detect MIME type
            filename = file.filename or "unknown"
            detected_mime = self._detect_mime_type(file_content, filename)

            if detected_mime not in self.config.ALLOWED_IMAGE_MIMES:
                raise MimeTypeError(
                    f"Invalid file type. Detected: {detected_mime}. Allowed: {', '.join(self.config.ALLOWED_IMAGE_MIMES)}",
                    filename=filename,
                    detected_mime=detected_mime,
                    allowed_mimes=list(self.config.ALLOWED_IMAGE_MIMES),
                )

            # Validate file signature (raises exceptions on failure)
            self._validate_file_signature(file_content, "image")

            logger.debug(
                "Image file validation passed: %s (%s, %s bytes)",
                filename,
                detected_mime,
                file_size,
            )
        except FileValidationError:
            # Let FileValidationError and subclasses propagate
            raise
        except Exception as err:
            logger.exception("Error during image file validation: %s", err)
            raise FileProcessingError(
                "File validation failed due to internal error",
                original_error=err,
            ) from err

    async def validate_zip_file(self, file: UploadFile) -> None:
        """
        Validate uploaded ZIP archive against service configuration.

        Args:
            file: Incoming ZIP file-like object to validate.

        Raises:
            FilenameSecurityError: Filename is empty, invalid, or fails
                security checks.
            ExtensionSecurityError: File extension is not allowed or is
                blocked.
            FileSizeError: File size exceeds maximum or file is empty.
            MimeTypeError: MIME type is not in allowed ZIP types.
            FileSignatureError: File signature doesn't match expected ZIP
                format.
            CompressionSecurityError: ZIP compression validation failed
                (zip bomb detected).
            FileProcessingError: Unexpected error during validation.
        """
        try:
            # Validate filename (raises exceptions on failure)
            self._validate_filename(file)

            # Validate file extension (raises exceptions on failure)
            self._validate_file_extension(file, self.config.ALLOWED_ZIP_EXTENSIONS)

            # Validate file size (raises exceptions on failure, returns content and size on success)
            file_content, file_size = await self._validate_file_size(
                file, self.config.limits.max_zip_size
            )

            # Detect MIME type using first 8KB
            filename = file.filename or "unknown"
            detected_mime = self._detect_mime_type(file_content, filename)

            # Validate ZIP file signature first (most reliable check)
            # This will raise FileSignatureError if signature doesn't match
            try:
                self._validate_file_signature(file_content, "zip")
            except FileSignatureError as err:
                # Re-raise with more specific message
                raise FileSignatureError(
                    "File content does not match ZIP format",
                    filename=filename,
                    expected_type="zip",
                ) from err

            # Check MIME type, but allow application/octet-stream if signature is valid
            # Some ZIP files are detected as octet-stream, but signature check ensures it's really a ZIP
            if detected_mime not in self.config.ALLOWED_ZIP_MIMES:
                if detected_mime == "application/octet-stream":
                    # Valid ZIP file, just detected as generic binary
                    logger.debug(
                        "ZIP file detected as application/octet-stream, but signature is valid: %s",
                        filename,
                    )
                else:
                    raise MimeTypeError(
                        f"Invalid file type. Detected: {detected_mime}. Expected ZIP file.",
                        filename=filename,
                        detected_mime=detected_mime,
                        allowed_mimes=list(self.config.ALLOWED_ZIP_MIMES),
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
                self.compression_validator.validate_zip_compression_ratio(
                    full_file_content, file_size
                )

            # Perform ZIP content inspection if enabled
            if self.config.limits.scan_zip_content:
                self.zip_inspector.inspect_zip_content(full_file_content)

            logger.debug(
                "ZIP file validation passed: %s (%s, %s bytes)",
                filename,
                detected_mime,
                file_size,
            )
        except FileValidationError:
            # Let FileValidationError and subclasses propagate
            raise
        except Exception as err:
            logger.exception("Error during ZIP file validation: %s", err)
            raise FileProcessingError(
                "File validation failed due to internal error",
                original_error=err,
            ) from err
